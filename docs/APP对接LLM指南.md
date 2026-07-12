# APP 对接 LLM 指南

> 供李雨晨参考，将 LLM 能力集成到 APP 中。

---

## 一、LLM 提供的 ROS2 接口

| 接口 | 类型 | 说明 |
|------|------|------|
| `/llm/parse_task` | Service `ParseTask.srv` | 自然语言 → 结构化任务 JSON |
| `/llm/generate_report` | Service `GenerateReport.srv` | 任务日志 → 巡检报告文本 |

---

## 二、核心用法：自然语言下发任务

### 调用方式

```dart
// 用户输入自然语言 → 调用 parse_task → 得到任务 JSON → 发给 task_manager

// 1. 调用 LLM 解析
final request = ParseTask.Request();
request.input_text = "巡检A/B/C三点，遇到障碍物停止";  // 用户说的话
final response = await parseTaskClient.call(request);

// 2. 解析返回的 JSON
final task = jsonDecode(response.task_json);

// 3. 如果是巡检任务（task_type == "patrol"），发给 task_manager
if (task['task_type'] == 'patrol') {
  final taskReq = TaskRequest();
  taskReq.task_type = task['task_type'];     // "patrol"
  taskReq.route = task['route'];             // ["A","B","C"]
  taskReq.params = jsonEncode({
    "source": "app",
    "raw_text": request.input_text,
  });
  taskRequestPublisher.publish(taskReq);
}
```

### API 模式 vs 规则模式

parse_task 内部自动选择：
- 有 DeepSeek API Key → AI 理解，支持复杂表达
- 无 API Key → 规则匹配，支持基本指令

两种模式返回的 JSON 格式完全一致，APP 无需区分。

---

## 三、信息查询（护工问机器人问题）

用户也可以在 APP 上问机器人问题，比如"到哪了？""前面有没有障碍物？"

### 调用方式

```dart
final request = ParseTask.Request();
request.input_text = "你到哪个点了？";
final response = await parseTaskClient.call(request);
final result = jsonDecode(response.task_json);

if (result['task_type'] == 'info') {
  // 这是一个信息查询，不是任务指令
  // 直接把 answer 展示给用户看
  String answer = result['answer'] ?? '暂无相关信息';
  showAnswerToUser(answer);
}
```

### 支持的查询类型

| 用户可能问的 | query_type | 回答来源 |
|-------------|-----------|---------|
| "看到了什么？""有没有人？" | vision | `/vision/detections` 缓存 |
| "到哪了？""还有多远？" | navigation | `/nav_status` 缓存 |
| "安全吗？""有障碍物吗？" | safety | `/obstacle_status` 缓存 |
| "任务进度？""在做什么？" | status | `/task/status` 缓存 |
| "整体情况怎么样？" | all | 综合以上全部 |

---

## 四、获取巡检报告

```dart
final request = GenerateReport.Request();
request.task_id = "task_abc123";  // 要查询的任务ID
final response = await reportClient.call(request);
// response.report_text 就是护工可读的报告文本，直接展示即可
```

报告示例：
```
      巡 检 交 班 报 告

巡检时间: 2025-06-20 14:13    结束时间: 2025-06-20 14:25

[结论] 基本正常，有少量注意事项。

巡视区域（共3处）: A -> B -> C

  A点: 看到: 行人
  B点: 看到: 障碍物
  C点: 看到: 行人、积水

[需要注意]
  - 走廊有障碍物，建议清理通道

（由智能巡检系统自动生成）
```

---

## 五、APP 需要订阅展示的 Topic

| Topic | 类型 | 展示内容 |
|-------|------|---------|
| `/task/status` | TaskStatus | 任务状态、步骤进度 |
| `/task/log` | TaskLog | 巡检事件日志 |
| `/nav_status` | NavStatus | 导航进度、剩余距离 |
| `/obstacle_status` | ObstacleStatus | 障碍物告警 |
| `/vision/detections` | DetectionArray | 检测目标 + 截图路径 |

> 注意：`vision/detections` 中的 `image_path` 字段是截图文件路径，
> APP 可以根据路径去读取图片文件并展示给护工。

---

## 六、推荐 APP 交互流程

```
┌──────────────────────────────────────────────────┐
│  APP 界面                                         │
│                                                    │
│  [巡检输入框] "巡检A/B/C三点"                      │
│  [语音按钮]  [发送按钮]                            │
│                                                    │
│  ── 机器人回答 ──                                  │
│  "好的，已开始巡检 A → B → C"                      │
│                                                    │
│  ── 实时状态栏 ──                                  │
│  正在导航 | 进度65% | 剩余1.2m                      │
│  检测到: 行人、积水                                 │
│                                                    │
│  [查看巡检报告] → 展示护工交班报告                  │
└──────────────────────────────────────────────────┘
```
