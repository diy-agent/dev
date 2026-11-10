/**
 * fixtures.ts —— UI 意图测试的**场景工厂**（##518）
 *
 * 造场景的方式是「拼一份 DevSnapshot」：它是纯 JSON，主进程算出来什么样，这里就造什么样。
 * 为什么不连真 core：UI 意图测的是「给这份数据，用户看到什么」；真 core 的产出由 core 自己的
 * 意图测试（进程内全栈）负责 —— 两层各自只测自己那一段（判据见 docs/test-ownership.md）。
 *
 * ⚠️ 字段随 `dev-core/shared` 变时这里会编译报错，这是故意的：快照形状是跨进程契约。
 */
import type { DevSnapshot, LaunchStatus, ExternalInstance } from "@diy-agent/dev-core/shared";

const WT = "/repo";
const WT2 = "/repo-worktrees/branch-b";

export function launch(over: Partial<LaunchStatus> = {}): LaunchStatus {
    const app = over.app ?? "chat";
    const id = over.launch ?? "lab";
    return {
        key: `${WT}\u0000${app}\u0000${id}`,
        repo: "/repo",
        worktree: WT,
        worktreeLabel: "main",
        worktreePath: "~/_diy",
        branch: "main",
        app,
        appTitle: app,
        launch: id,
        launchTitle: id,
        command: `./sha.sh ${id}`,
        env: {},
        appDir: `${WT}/apps/${app}`,
        yamlPath: `${WT}/apps/${app}/app.yaml`,
        home: `${WT}/build/${id}/home`,
        homeDeclared: false,
        configIssues: [],
        nodeId: null,
        uri: null,
        built: true,
        running: false,
        starting: false,
        entries: [],
        instances: [],
        runtime: null,
        ...over,
    } as LaunchStatus;
}

export function snapshot(over: Partial<DevSnapshot> = {}): DevSnapshot {
    const launches = over.launches ?? [launch()];
    return {
        repoRoot: "/repo",
        repoName: "_diy",
        repoBranch: "main",
        registryDir: "/tmp/registry",
        worktreeCount: 1,
        appCount: 1,
        runningCount: launches.filter((l) => l.running).length,
        problems: [],
        externals: [],
        launches,
        worktreeInstances: {},
        ...over,
    } as DevSnapshot;
}

/** 一个在跑的 launch（带 runtime / instances，供「详情显示 PID 端口」这类断言用） */
export function runningLaunch(over: Partial<LaunchStatus> = {}): LaunchStatus {
    const base = launch({ running: true });
    return launch({
        ...over,
        running: true,
        instances: [
            {
                pid: 4242,
                launch: base.launch,
                name: "",
                displayName: `${base.app}#4242`,
                diyHome: base.home,
                startedAt: "2026-11-10T10:00:00.000Z",
                port: 18888,
            },
        ],
        runtime: {
            pid: 4242,
            port: 18888,
            startedAt: "2026-11-10T10:00:00.000Z",
            uptimeMs: 125_000,
            memBytes: 64 * 1024 * 1024,
            cmdline: "electron build/app/main/index.mjs",
            cwd: base.appDir,
            diyHome: base.home,
        },
    });
}

export function external(over: Partial<ExternalInstance> = {}): ExternalInstance {
    return {
        pid: 999,
        app: "diy-app",
        launch: null,
        diyHome: "/Users/someone/.diy",
        worktree: null,
        startedAt: "2026-11-10T09:00:00.000Z",
        port: 18888,
        production: true,
        ...over,
    };
}

export { WT, WT2 };
