# Direct Voice Motion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute recognized short voice movement commands directly while preventing conversational replies from triggering motion.

**Architecture:** `doubao_voice_node` will be instructed to emit a concise `执行任务：<command>` response for a supported motion request. `voice_command_router_node` will forward only this marked response to `/llm/user_command`; all other assistant text remains conversational. The existing LLM bounded-motion tool, velocity mux, obstacle avoidance, and emergency stop remain unchanged.

**Tech Stack:** Python, ROS 2 Foxy, rclpy, unittest, colcon.

---

### Task 1: Lock the routing boundary with tests

**Files:**
- Create: `voice/voice_control/test/test_voice_command_router.py`
- Modify: `voice/voice_control/voice_control/voice_command_router_node.py:87-119`

- [ ] **Step 1: Write the failing tests**

```python
def test_plain_assistant_confirmation_is_not_forwarded_to_llm(router):
    router._route_completed_turn("将前进一秒，请确认是否执行")
    assert router.sent_commands == []

def test_marked_motion_is_forwarded_to_llm(router):
    router._route_completed_turn("执行任务：前进一秒")
    assert router.sent_commands == ["前进一秒"]
```

- [ ] **Step 2: Run the tests to verify the first test fails**

Run: `python -m unittest voice/voice_control/test/test_voice_command_router.py`

Expected: the plain confirmation test fails because it is currently forwarded to the LLM.

- [ ] **Step 3: Implement the minimal routing change**

```python
def _route_completed_turn(self, text):
    if not text or CONTROL_PREFIX not in text:
        return
    command = text.split(CONTROL_PREFIX, 1)[1].strip()
    command = re.split(r"[。！\n]", command, maxsplit=1)[0].strip()
    if not command or command == self._last_command:
        return
    self._send_to_llm(command)
    self._last_command = command
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest voice/voice_control/test/test_voice_command_router.py`

Expected: both tests pass.

- [ ] **Step 5: Commit the routing fix**

```bash
git add voice/voice_control/voice_control/voice_command_router_node.py voice/voice_control/test/test_voice_command_router.py
git commit -m "fix: gate voice motion on execution marker"
```

### Task 2: Make direct motion replies concise

**Files:**
- Modify: `voice/voice_control/voice_control/doubao_voice_node.py:70-86`
- Test: `voice/voice_control/test/test_doubao_voice_prompt.py`

- [ ] **Step 1: Write the failing prompt test**

```python
def test_system_role_requires_direct_marked_motion_output():
    assert "不要求二次确认" in DEFAULT_SYSTEM_ROLE
    assert "执行任务：<原始移动指令>" in DEFAULT_SYSTEM_ROLE
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m unittest voice/voice_control/test/test_doubao_voice_prompt.py`

Expected: it fails because the current role requests confirmation.

- [ ] **Step 3: Replace the confirmation rule**

```python
"当用户发出前进、后退、左移、右移、左转或右转等短时移动指令时，不要求二次确认。"
"只回复「执行任务：<原始移动指令>」，不要补充解释。"
"普通问候、问答和说明不使用「执行任务：」前缀。"
```

- [ ] **Step 4: Run the prompt test to verify it passes**

Run: `python -m unittest voice/voice_control/test/test_doubao_voice_prompt.py`

Expected: PASS.

- [ ] **Step 5: Commit the direct-response prompt**

```bash
git add voice/voice_control/voice_control/doubao_voice_node.py voice/voice_control/test/test_doubao_voice_prompt.py
git commit -m "feat: make voice motion execute directly"
```

### Task 3: Build and validate on the car

**Files:**
- No source changes.

- [ ] **Step 1: Rebuild only the voice package in the car container**

Run inside `/root/icar_ros2_ws/icar_ws`:

```bash
source /opt/ros/foxy/setup.bash
colcon build --packages-select voice_control
```

- [ ] **Step 2: Restart only `doubao_voice_node` and `web_voice_gateway_node`**

Start both with `ROS_DOMAIN_ID=30`; preserve the existing injected `DOUBAO_APP_ID` and `DOUBAO_ACCESS_KEY` environment values for the former.

- [ ] **Step 3: Validate graph and browser gateway**

```bash
ros2 topic info /voice/web_audio -v
ros2 topic info /llm/user_command -v
```

Expected: web gateway publishes audio, doubao subscribes, and router is the only voice-to-LLM publisher for marked commands.

- [ ] **Step 4: Physical safety test**

With wheels raised or an unobstructed area, say “前进一秒”. Verify a concise voice reply and one bounded forward movement. Say a normal conversational sentence containing “前进” and verify no movement.

