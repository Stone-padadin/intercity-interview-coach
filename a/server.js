const path=require('node:path');
const fs=require('node:fs');
const crypto=require('node:crypto');
const express=require('express');
const multer=require('multer');
const mammoth=require('mammoth');
const {PDFParse}=require('pdf-parse');
const Database=require('better-sqlite3');

const app=express();
const port=Number(process.env.PORT||8765);
const uploadDir=path.join(__dirname,'uploads');
fs.mkdirSync(uploadDir,{recursive:true});
const db=new Database(path.join(__dirname,'interview-practice.db'));
db.pragma('journal_mode = WAL');
db.exec(`CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  candidate_name TEXT,
  resume_file TEXT,
  professional TEXT,
  target TEXT,
  skills TEXT,
  project_name TEXT NOT NULL,
  contribution TEXT,
  technical_plan TEXT,
  debugging TEXT,
  result TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
)`);
const saveProject=db.prepare(`INSERT INTO projects (session_id,candidate_name,resume_file,professional,target,skills,project_name,contribution,technical_plan,debugging,result,created_at,updated_at) VALUES (@session_id,@candidate_name,@resume_file,@professional,@target,@skills,@project_name,@contribution,@technical_plan,@debugging,@result,@created_at,@updated_at)`);
const upload=multer({dest:uploadDir,limits:{fileSize:10*1024*1024},fileFilter:(req,file,done)=>{
  const ext=path.extname(file.originalname).toLowerCase();
  const allowed=['.pdf','.doc','.docx'];
  if(!allowed.includes(ext))return done(new Error('INVALID_FILE_TYPE'));
  done(null,true);
}});

app.use((req,res,next)=>{
  res.setHeader('Access-Control-Allow-Origin','*');
  res.setHeader('Access-Control-Allow-Headers','Content-Type');
  res.setHeader('Access-Control-Allow-Methods','GET,POST,OPTIONS');
  if(req.method==='OPTIONS')return res.sendStatus(204);
  next();
});

function detectCandidateName(text){
  const lines=text.split(/\r?\n/).map(line=>line.trim()).filter(Boolean).slice(0,12);
  const ignored=/简历|个人信息|教育经历|求职意向|求职方向|工作经历|项目经历|技能|电话|手机|邮箱|电子信息|工程师|应聘|resume/i;
  return lines.find(line=>/^[\u4e00-\u9fff]{2,4}$/.test(line)&&!ignored.test(line))||'';
}

app.use(express.json());
app.use(express.static(__dirname));

app.get('/api/health',(req,res)=>res.json({ok:true,service:'resume-parser'}));

app.post('/api/projects',(req,res)=>{
  const input=req.body||{};
  if(!String(input.project_name||'').trim())return res.status(400).json({error:'项目名称不能为空'});
  const now=new Date().toISOString();
  const project={
    session_id:String(input.session_id||crypto.randomUUID()),
    candidate_name:String(input.candidate_name||''),resume_file:String(input.resume_file||''),
    professional:String(input.professional||''),target:String(input.target||''),skills:String(input.skills||''),
    project_name:String(input.project_name).trim(),contribution:String(input.contribution||''),
    technical_plan:String(input.technical_plan||''),debugging:String(input.debugging||''),result:String(input.result||''),
    created_at:now,updated_at:now
  };
  const saved=saveProject.run(project);
  res.status(201).json({id:saved.lastInsertRowid,...project});
});

app.get('/api/projects/:sessionId',(req,res)=>{
  const project=db.prepare('SELECT * FROM projects WHERE session_id = ? ORDER BY id DESC LIMIT 1').get(req.params.sessionId);
  if(!project)return res.status(404).json({error:'未找到项目记录'});
  res.json(project);
});

app.post('/api/resume/parse',upload.single('resume'),async(req,res)=>{
  if(!req.file)return res.status(400).json({error:'请上传 PDF、DOC 或 DOCX 文件'});
  try{
    const ext=path.extname(req.file.originalname).toLowerCase();
    let text='';
    if(ext==='.pdf'){
      const parser=new PDFParse({data:fs.readFileSync(req.file.path)});
      const parsed=await parser.getText();
      text=parsed.text;
      await parser.destroy();
    }else if(ext==='.docx'){
      const parsed=await mammoth.extractRawText({path:req.file.path});
      text=parsed.value;
    }else{
      return res.status(415).json({error:'暂不支持旧版 DOC，请另存为 DOCX 或 PDF'});
    }
    const normalized=text.replace(/\r\n/g,'\n').replace(/[ \t]+\n/g,'\n').trim();
    if(!normalized)return res.status(422).json({error:'没有提取到文字，请上传可复制文字的 PDF 或 DOCX 简历'});
    res.json({fileName:req.file.originalname,text:normalized,size:req.file.size,characters:normalized.length,candidateName:detectCandidateName(normalized)});
  }catch(error){
    res.status(422).json({error:'简历解析失败，请检查文件内容后重试'});
  }finally{
    fs.rm(req.file.path,{force:true},()=>{});
  }
});

app.use((error,req,res,next)=>{
  if(error?.code==='LIMIT_FILE_SIZE')return res.status(413).json({error:'文件不能超过 10 MB'});
  if(error?.message==='INVALID_FILE_TYPE')return res.status(415).json({error:'请上传 PDF、DOC 或 DOCX 文件'});
  if(error) return res.status(500).json({error:'上传服务暂时不可用，请稍后重试'});
  next();
});

app.listen(port,()=>console.log(`Interview practice server: http://127.0.0.1:${port}`));
