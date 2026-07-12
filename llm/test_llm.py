"""
LLM模块测试脚本
==============
功能：
  - run_deepseek_connection_test(): 测试DeepSeek API连接
  - run_protocol_validation(): 测试JSON协议校验
  - run_command_test(): 测试命令解析模式（真实API）
  - run_tool_test(): 测试工具调用模式（真实API）

前置条件：
  - 设置环境变量 DEEPSEEK_API_KEY
  - 或创建 .env 文件（参考 .env.example）

注意：此测试会调用真实的DeepSeek API，需要网络连接并消耗API额度
运行方式：
  python test_llm.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from llm_gateway_node import LLMGatewayNode


def run_command_test():
    print("=" * 60)
    print("LLM Gateway Command Test (Real DeepSeek API)")
    print("=" * 60)
    print("注意: 此测试会调用真实的 DeepSeek API，需要网络连接")
    print("=" * 60)

    gateway = LLMGatewayNode(tool_mode=False)

    test_inputs = [
        "向前走2米",
        "左转90度",
        "检测前方有没有积水",
    ]

    for user_input in test_inputs:
        print(f"\n测试: {user_input}")
        try:
            result = gateway.parse_task(user_input)
            if result.get("success"):
                cmd = result["command"]
                print(f"✓ 成功 - 类型: {cmd['type']}, Payload: {cmd['payload']}")
            else:
                print(f"✗ 失败: {result.get('error', '未知错误')}")
        except Exception as e:
            print(f"✗ 异常: {str(e)}")


def run_tool_test():
    print("\n" + "=" * 60)
    print("LLM Gateway Tool Call Test (Real DeepSeek API)")
    print("=" * 60)
    print("注意: 此测试会调用真实的 DeepSeek API")
    print("注意: 工具执行需要 ROS2 环境，否则会返回未初始化错误")
    print("=" * 60)

    gateway = LLMGatewayNode(tool_mode=True)

    test_inputs = [
        "巡检 A、B、C 三个点",
        "停下",
        "当前状态是什么",
        "向后走5米",
    ]

    for user_input in test_inputs:
        print(f"\n测试: {user_input}")
        try:
            result = gateway.process_user_input(user_input)
            if result.get("success"):
                tool_name = result.get("tool_name", "")
                print(f"✓ 成功 - 工具: {tool_name}")
                if "payload" in result:
                    print(f"  参数: {result['payload']}")
            else:
                print(f"✗ 失败: {result.get('message', '未知错误')}")
        except Exception as e:
            print(f"✗ 异常: {str(e)}")


def run_protocol_validation():
    print("\n" + "=" * 60)
    print("测试协议校验功能")
    print("=" * 60)

    from json_protocol import TaskCommand

    test_json = {
        "version": "1.0",
        "type": "move",
        "mode": "single",
        "payload": {"command": "forward", "distance": 2.0, "speed": 50},
        "priority": 5,
        "timeout": 30
    }

    try:
        cmd = TaskCommand(**test_json)
        if cmd.is_valid():
            print("✓ 协议校验通过")
            return True
        else:
            print("✗ 校验失败")
            return False
    except Exception as e:
        print(f"✗ 异常: {str(e)}")
        return False


def run_deepseek_connection_test():
    print("\n" + "=" * 60)
    print("测试 DeepSeek API 连接")
    print("=" * 60)

    from deepseek_client import DeepSeekClient

    client = DeepSeekClient()
    print(f"API Key: {client.api_key[:8]}...")
    print(f"Base URL: {client.base_url}")
    print(f"Model: {client.model}")

    try:
        import requests
        response = requests.get(f"{client.base_url}/v1/models", headers=client.headers, timeout=10)
        if response.status_code == 200:
            print("✓ API 连接成功")
            return True
        else:
            print(f"✗ API 连接失败: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ 连接异常: {str(e)}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("LLM Gateway 真实 API 测试")
    print("=" * 60)
    print("警告: 此测试会调用真实的 DeepSeek API，会消耗 API Key 额度")
    print("=" * 60)

    confirm = input("继续测试? (y/N): ").strip().lower()
    if confirm != 'y':
        print("测试已取消")
        sys.exit(0)

    run_deepseek_connection_test()
    run_protocol_validation()
    run_command_test()
    run_tool_test()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)