# C 视觉接口 v0.1 · 当前实现，待 A/B/D 联调确认

## B 的固件调用

头文件以 `c/firmware/apps/main/pose/c_live_pose.h` 为准。主工程启动模型与缓冲区后，摄像头回调提交有效 UYVY 帧；模型线程复制取流数据，不保存驱动指针。获取最新结果使用 `c_live_pose_get_latest`，具体参数类型见头文件，避免重新声明不兼容结构。

关键语义：`has_person` 表示检测到人；`calibration_state` 为 IDLE=0、COLLECTING=1、READY=2、REJECTED=3；`calibrated_raw` 和 `stable_state` 为 UNKNOWN=0、NEUTRAL=1、DEVIATION=2。`valid` 才表示姿态结果当前可用。未标定、多人、缺少必要关键点、超距、失败和超过 6000 ms 过期均不可沿用历史提醒。

旧 SDK `status/error` 是原始启发式标签，不可作为产品姿态反馈。仅标定后持续肩线侧倾可进入当前演示，不用它给心理、医学或整体面试能力评分。

## 诊断串口

live 使用 115200 波特。命令 `posecal` 加回车触发显式标定，非持久化。启动后必须重新标定。

```text
CPOSE frame=<id> capture_ms=<u32> infer_ms=<ms> status=<legacy> error=<legacy> stable=<0..2> valid=<0|1> err=<code> internal=<bytes> psram=<bytes>
CCAL frame=<id> people=<0|1> state=<0..3> samples=<n> raw=<0..2> stable=<0..2> valid=<0|1> angle_md=<int> delta_md=<int> base_md=<int> enter_md=<int> noise_md=<int>
```

CCAL 的 `people` 是布尔存在标记，不是人数；整数角度单位为毫度。CPOSE 的 `capture_ms` 受设备格式化输出限制为低 32 位，不等于墙钟时间，不适合跨重启排序。帧号间隔体现丢弃忙帧，不能拿摄像头帧率当推理频率。

USB preview 使用独立固件，921600 波特；包头 `<8sIHHII` 共 24 字节、小端：magic `CVJPG001`、序号、宽、高、JPEG 长度、CRC32，后接 JPEG。CRC 错误帧丢弃并重新同步。

## 标定与去抖

10 个连续有效样本；单人、score >= 0.55、鼻与双肩不贴边，肩宽 >= 30 px 且 >= 图宽 20%。角度中位数为基准；角度范围 >18 度、MAD >3 度、基准绝对角 >30 度或肩宽不稳定则拒绝。

侧倾进入阈值 max(12 度,4*MAD+3 度)，回正阈值为其 65%。偏离需至少 3 个样本且持续 >=1500 ms；回正需 2 样本且 >=500 ms。实测约 2 秒一次推理，偏离提醒至少跨约 4 秒的采样跨度，另加处理延迟；不能宣传毫秒级提醒或可靠捕捉快速抖动。这些是待真人验证的工程参数。

## 尚未实现的共享传输

C 到网页/Agent 的网络消息、统一时钟、会话 ID、反馈触发仲裁尚未实现。A/B/D 不要假定本机预览就是正式产品 API。B 与 C 确认传输和数据有效性后再版本化；D 定义何时提醒，避免中断面试回答。
