# Flutter APK 与网页控制开发交接

日期：2026-07-13  
仓库：`/Users/xionghaoyu/icar-ros2-patrol`  
分支：`dev`

## 当前状态

- 当前 `HEAD`：`e97c4c4`
- 已推送至 `origin/dev`
- 小车地址：`192.168.137.117`
- 小车服务端口：`6500`
- ROS Domain ID：`30`
- 网页控制、WebSocket、原始视频和 YOLO 标注视频在 Mac 端均已验证正常。

## 本会话完成内容

### 1. 恢复并整合 Flutter App

- 核对发现完整 Flutter UI 原先主要位于 `mobile` 分支，`dev` 曾出现文件缺失和混合状态。
- 已把完整 App、`dev` 的控制安全逻辑及最新车端协议整合。
- App 默认连接地址统一为 `192.168.137.117:6500`。
- 旧 APK 保存的 `192.168.137.218` 会自动迁移到 `.117`。

### 2. 与网页统一通信协议

- WebSocket：`ws://192.168.137.117:6500/ws/control`
- 原始视频：`http://192.168.137.117:6500/video_feed`
- YOLO 视频：`http://192.168.137.117:6500/yolo_video_feed`
- 健康检查：`http://192.168.137.117:6500/health`
- 方向控制使用 JSON 指令并携带速度。
- 长按方向键期间每 100ms 发送一次心跳。
- 松手、App 进入后台或页面销毁时发送停车指令。

### 3. 修复 Flutter MJPEG 视频

根因：Flutter 的 `Image.network` 不能可靠解析小车返回的持续 MJPEG `multipart/x-mixed-replace` 响应。

修复：

- 新增 `lib/widgets/mjpeg_stream_view.dart`。
- 从 HTTP 流中按 JPEG SOI/EOI 标记拆分帧。
- `lib/pages/vision_page.dart` 已真正改用 `MjpegStreamView`。
- 支持原始画面和 YOLO 标注画面切换。

对应提交：

```text
d4c0c30 fix(flutter): render car MJPEG stream on Android
```

### 4. 修复 Android 网络配置

已加入：

- `android.permission.INTERNET`
- `android.permission.ACCESS_NETWORK_STATE`
- `android.permission.NEARBY_WIFI_DEVICES`
- `android.permission.ACCESS_LOCAL_NETWORK`
- `android:usesCleartextTraffic="true"`

`MainActivity` 会在 Android 13 及以上请求“附近设备”权限，以兼容 Android 16 的局域网保护场景。

Android 官方参考：

<https://developer.android.com/privacy-and-security/local-network-permission>

对应提交：

```text
e97c4c4 fix(android): request local network access
```

### 5. Android 工程纳入 Git

- 原 `.gitignore` 错误地忽略整个 `android/`。
- 已提交 Android Manifest、Gradle 配置、启动 Activity、资源和图标。
- NDK 配置为 `28.2.13676358`。
- 包名为 `com.icar.icar_app`。

## 最新 APK

文件：

```text
/Users/xionghaoyu/icar-ros2-patrol/build/app/outputs/flutter-apk/icar-app-2.0.2-build4.apk
```

信息：

```text
版本：2.0.2+4
包名：com.icar.icar_app
大小：约 51.2 MB
SHA-256：f66e317ecc1b29f6fafe966915d1e3f643d6b46b3cbe3c0b3b67eda8007b68ac
```

Mac 当前通过临时 HTTP 服务提供局域网下载：

```text
http://192.168.137.69:8090/icar-app-2.0.2-build4.apk
```

Mac IP 变化或 HTTP 服务停止后，该链接需要重新生成。

## 已完成验证

- `flutter analyze`：0 问题。
- `flutter test`：全部通过。
- `flutter build apk --release`：成功。
- APK Manifest 中包含网络及局域网权限。
- 小车 `/health` 返回：

```json
{
  "bridge_ready": true,
  "camera": {
    "annotated_ready": true,
    "error": null,
    "raw_ready": true,
    "ready": true,
    "source": "ros_mjpeg"
  }
}
```

- 直接绕过网页代理连接以下地址成功：

```text
ws://192.168.137.117:6500/ws/control
```

- 订阅 `detections` 后收到：

```json
{"topic":"subscription","subscribed":"detections"}
```

因此车端 `6500` WebSocket 和 HTTP/MJPEG 服务正常。

## 网页与 App 的通信差异

网页链路：

```text
Mac 网页 -> 本机 8765/8766 代理 -> 小车 192.168.137.117:6500
```

App 链路：

```text
Android 手机 -> 直接访问小车 192.168.137.117:6500
```

网页正常只能证明 Mac 到小车正常，不能证明手机的 Wi-Fi 路由、权限、VPN 或移动数据策略正常。

## 下一会话优先事项

用户尚未确认安装 `2.0.2+4` 后 App 是否恢复通信和视频。

1. 确认手机安装的应用版本为 `2.0.2`。
2. 安装或首次启动时允许“附近设备”权限。
3. 确认手机与小车处于同一 Wi-Fi。
4. 在手机浏览器打开：

   ```text
   http://192.168.137.117:6500/health
   ```

5. 如果手机浏览器打不开：
   - 暂停 VPN 和代理。
   - 暂时关闭移动数据，避免系统切换路由。
   - 确认手机没有因 Wi-Fi 无互联网而自动断开。
6. 如果浏览器能打开但 App 不能连接：
   - 使用 USB 或无线 ADB 连接手机。
   - 查看 `com.icar.icar_app` 的 `logcat`。
   - 检查 App 设置中的 IP 为 `192.168.137.117`、端口为 `6500`。
7. 如果控制通信正常但视频不显示：
   - 检查 App 日志中的“正在请求 MJPEG”“MJPEG 流已接通”或异常信息。
   - 真机调试 `MjpegStreamView` 的 HTTP 响应和首帧解析。

当前没有 ADB 设备连接，因此尚未完成 Android 真机端到端验证。

## 构建环境

```text
ANDROID_HOME=/Users/xionghaoyu/android-sdk
ANDROID_SDK_ROOT=/Users/xionghaoyu/android-sdk
JAVA_HOME=/opt/homebrew/opt/openjdk@21
Flutter=/opt/homebrew/bin/flutter
Android SDK=36.0.0
NDK=28.2.13676358
```

已执行 `flutter precache --android --force`，Flutter 缓存中的 `impellerc` 已恢复。废纸篓里的 `impellerc` 不需要使用或双击运行。

## 工作区注意事项

以下内容不属于本次 Flutter/App 修复，请勿随意提交或删除：

```text
M  llm/llm_gateway/llm_gateway/llm_gateway_node.py
?? icar_app.iml
?? 碎玉轩小曲.m4a
```

处理新改动时应继续避免把这些文件混入 Flutter 提交。
