# 提醒裁决策略原型（仅软件）

纯 Python 策略原型，不对接设备、网络、音频或浏览器。用于等值模拟“检测到持续侧倾→决定是否排队一条语音提醒”的逻辑决策，供未来集成到真实提醒链路前先行验证。

## 这不是什么

- 不是接线/实验事故检测。输入只能是 `normal`/`deviated`/`unknown` 三态，没有“接线错误”或“故障”标签。
- 不是真实语音播放。`pending_voice`/`voice_intent` 只是供调度器取用的“意图”；返回意图不代表已经说话。
- 不代表当前板上固件已开启检测或提醒（厂商树未查到 B 提醒运行模块接入，见 [历史源码核查](../../../docs/ljyd/检测提醒能力核查.md)）。

## 策略规则（21 项测试全部通过）

- 事件必须显式标记来源 `synthetic` 或 `real`；单实例只接受一种来源。
- 仅在 `online && visual_opt_in && phase=='active'` 时接受事件；断连/退出视觉/非 active 阶段清空排队中的提醒。
- 无效、未知状态、未来时间、超过 6 秒过期、乱序/重复帧都拒绝。
- 维护姿势有效期 6 秒；无新有效数据即回 `unknown`。
- 语音默认关闭；开启后同一次持续偏离最多发一条意图，回正后才能重置一次用量。
- 一次提醒至少间隔 60 秒（cooldown 下限），不打断助教正在说话；助教忙时先挂起，一旦说话完成且未过期再发，过期/断连/用户关闭即取消。
- `set_voice_enabled(False)`、断连或退出视觉立即撤销挂起的提醒。
- 返回的意图带 `source`、`frame_id`、`expires_ms`，文本不含“接线”等错误结论。

## 使用

```python
from alert_policy import AlertPolicy, Context, PoseEvent
p = AlertPolicy(source='synthetic', voice_enabled=True)
d = p.update(now_ms=100,
             context=Context('active', True, True, False),
             event=PoseEvent('synthetic', 1, 100, 'deviated', True))
```

测试：

```powershell
python -m unittest -v test_alert_policy
```

## 未来集成约束（未在本原型中实现）

- 真实调度器必须重新校验“发出时”的最新 context 与过期时间，策略只是决策模块。
- 接入真实姿势事件时改 `source='real'`，不得把合成事件标成真实。
- 若以后接 TTS，应定义不打断、用户可关、每次持续偏离只播一次、回正重置、冷却和会话过期规则，并补真实硬件的可见可听验收。