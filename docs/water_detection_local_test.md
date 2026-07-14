# 积水识别本地测试方法

目标：在不上车的情况下，验证 `models/water_seg_v1.pt` 对教室走廊、低分辨率摄像头、透明积水场景的可用性。

## 1. 干地误报基线

先对准没有积水的教室或走廊，跑 20 到 60 帧。这个结果用于判断模型会不会把反光、地砖纹理、玻璃、灯光亮斑误报成 water。

```powershell
cd D:\北交大两周项目\code_repos\icar-ros2-patrol-yolo-obstacle

python vision\water_eval.py `
  --source 0 `
  --model models\water_seg_v1.pt `
  --tag dry_baseline `
  --frames 60 `
  --camera-size 640x480 `
  --eval-size 640x480 `
  --imgsz 320 `
  --conf 0.25 `
  --min-area-ratio 0.002 `
  --device cpu
```

建议通过标准：

- `positive_rate` 接近 `0`。
- `max_consecutive_positive` 不超过 `1`。
- 保存的标注图里没有持续框住灯光反射或地砖纹理。

## 2. 透明积水实测

用同一个机位，在走廊或教室地面放一小片浅水。透明水不明显时，尽量拍到水边缘、反光边界或湿滑区域，而不是只拍纯透明区域。

```powershell
python vision\water_eval.py `
  --source 0 `
  --model models\water_seg_v1.pt `
  --tag transparent_water_640 `
  --frames 60 `
  --camera-size 640x480 `
  --eval-size 640x480 `
  --imgsz 320 `
  --conf 0.25 `
  --min-area-ratio 0.002 `
  --device cpu
```

如果完全识别不到，再跑一版低阈值敏感测试：

```powershell
python vision\water_eval.py `
  --source 0 `
  --model models\water_seg_v1.pt `
  --tag transparent_water_sensitive `
  --frames 60 `
  --camera-size 640x480 `
  --eval-size 320x240 `
  --imgsz 320 `
  --conf 0.15 `
  --min-area-ratio 0.001 `
  --device cpu
```

低阈值只用于判断模型有没有一点响应。若低阈值才偶尔报，实车不要直接当可靠告警用，至少要做连续多帧确认。

## 3. 图片或视频批量测试

图片目录：

```powershell
python vision\water_eval.py `
  --source D:\water_samples\corridor `
  --model models\water_seg_v1.pt `
  --tag corridor_images `
  --eval-size 640x480 `
  --imgsz 320 `
  --conf 0.25 `
  --min-area-ratio 0.002
```

视频：

```powershell
python vision\water_eval.py `
  --source D:\water_samples\corridor_water.mp4 `
  --model models\water_seg_v1.pt `
  --tag corridor_video `
  --frames 120 `
  --sample-every 3 `
  --eval-size 640x480 `
  --imgsz 320 `
  --conf 0.25 `
  --min-area-ratio 0.002
```

## 4. 结果文件

每次运行会生成一个目录：

```text
local_detection_samples/water_eval/<tag>_<timestamp>/
```

重点看：

- `summary.json`：总体识别率、最大连续识别帧数。
- `frames.csv`：每帧是否识别到水、最大置信度、面积比例。
- `frames.jsonl`：每帧 bbox 和置信度详情。
- `frames/*.jpg`：带框截图，用来人工确认是否框到了真实积水。

## 5. 判断标准

建议先按这个粗标准决策：

- 干地误报：`positive_rate <= 0.05`，且没有连续 3 帧以上误报。
- 透明积水召回：`positive_rate >= 0.5`，或同一片水能连续 5 帧以上被框住。
- 若透明积水只能在 `conf=0.15` 下偶尔出现，说明模型对当前走廊透明水不稳，上车时只适合做辅助提示，不适合直接触发强告警或停车。

上车前推荐参数先用：

```text
water_confidence=0.25
water_imgsz=320
water_min_area_ratio=0.002
inference_frame_stride=15~30
```

如果透明水漏检严重，再临时试：

```text
water_confidence=0.15
water_min_area_ratio=0.001
```

但必须配合连续多帧确认，否则走廊灯光反射容易误报。
