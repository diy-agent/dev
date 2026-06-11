"""ShellTest API 意图测试。

每个测试 = ShellTest 的一条可执行需求文档。
形式参考 test_dai_task_intent.py——干净的 setup，直接验证契约，
使用 assert_session 做多行 transcript 式断言。
"""

from _shelltest import ShellTest


def test_intent_exit_code_direct():
    """退出码从 PS1 内嵌的 $? 自动捕获，不需要命令里 echo $?。

    也不拦截非零退出码——像真 bash 一样，$? 自取。
    """
    sh = ShellTest()
    sh.assert_session("! true")
    sh.assert_session("! false; echo $?\n1")


def test_intent_separate_channels():
    """stdout 和 stderr 各自独立返回，不混淆。"""
    ShellTest().assert_session("""
        ! echo out; echo err >&2
        out
        ---
        err
    """)


def test_intent_stateful_session():
    """环境变量跨 run() 持久。

    用显式 session() 而非 assert_session() 来展示状态保持。
    ShellTest 不开进程，.session() 才开。
    """
    with ShellTest().session() as s:
        s.run("export MSG=world")
        code, out, _ = s.run("echo $MSG")
        assert code == 0
        assert out == "world"


def test_intent_error_output_separate():
    """命令失败时 stderr 有内容，stdout 空，后续命令不受影响。

    assert_session 内部自动开/关 session。
    """
    ShellTest().assert_session("""
        ! cat /nonexistent_file_xyz
        ---
        {{regex:.*No such file.*}}

        ! echo still ok
        still ok
    """)


def test_intent_sentinel():
    """{{*}} 匹配任意内容，{{regex:...}} 匹配正则。"""
    ShellTest().assert_session("""
        ! echo '任务 #42 创建成功'
        任务 {{*}} 创建成功

        ! echo '2026-06-10 12:00:00  INFO 启动完成'
        {{regex:\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}}} {{*}} INFO {{*}}
    """)
