// shared.ts — 主进程与 renderer 共用的**纯类型**（两端各打包一次，运行时没有模块依赖）。
//
// ##502 第二轮的四层模型：worktree → app → launch → entries。
//   · 静态清单 = `git worktree list` × `apps/*/app.yaml`（**不读注册表**）
//   · 动态状态 = `~/.diy-instances/*.json`，按 `(worktree, app, launch)` 对回静态清单
//
// 表单形状只在这里定义一次：主进程按它回，renderer 按它画。

/** app.yaml 里的一个入口（静态声明，不是运行时探测） */
export interface EntrySpec {
    readonly kind: "app" | "web";
    readonly title?: string;
    /** kind=web 时的默认地址（配置端口；实际端口可能被冲突挤走） */
    readonly url?: string;
}

/** app.yaml 里的一条启动命令 */
export interface LaunchSpec {
    readonly id: string;
    readonly title?: string;
    /** 在 app 目录下执行，如 `./sha.sh lab` */
    readonly command: string;
    /** 额外环境变量（如 web 的 PORT） */
    readonly env?: Readonly<Record<string, string>>;
    /**
     * 数据根（相对 worktree 根）；缺省 `build/lab/home`（apps/* 的 sha.sh 同一口径）。
     * 实例 URI 的 nodeId 从 `<worktree>/<home>/instance-id` 读。
     */
    readonly home?: string;
    readonly entries: readonly EntrySpec[];
}

/** 一个 app（= 一个 `apps/<name>/app.yaml`） */
export interface AppSpec {
    /** app 名（缺省 = 目录名）；注册表里的 `app` 允许写作 `name` 或 `diy-<name>` */
    readonly name: string;
    readonly title: string;
    /** app 目录绝对路径 */
    readonly dir: string;
    readonly launches: readonly LaunchSpec[];
}

/** `git worktree list` 的一行 */
export interface WorktreeInfo {
    readonly path: string;
    /** 分支短名；detached HEAD = null */
    readonly branch: string | null;
}

/** app.yaml 的配置错误（不阻止用，但必须让人看见：错了还默默按缺省跑 = 排查时最坑） */
export interface LaunchConfigIssue {
    readonly code: "home-missing" | "home-duplicate";
    readonly message: string;
    /** 给用户看的修法（一句话，含要写什么） */
    readonly fix: string;
}

/** 一个入口此刻的样子 */
export interface EntryStatus extends EntrySpec {
    /** 可点的地址（web 且运行时已知实际端口 ⇒ 用实际端口） */
    readonly href: string | null;
    /** 配置里写的地址；与实际不一致时 UI 两个都显示 */
    readonly configuredUrl: string | null;
    /** 实际端口 ≠ 配置端口 */
    readonly portMismatch: boolean;
}

/** 运行时事实（来自注册表 + 进程表） */
export interface LaunchRuntime {
    readonly pid: number;
    readonly port: number | null;
    readonly startedAt: string;
    /** 已运行毫秒 */
    readonly uptimeMs: number;
    /** 常驻内存字节数；取不到 = null */
    readonly memBytes: number | null;
    readonly cmdline: string;
    readonly cwd: string;
    readonly diyHome: string;
}

/** 一个在跑的实例（同一 launch 可以有多份 —— 靠**数据根**区分，不靠编号；名字由实例自报，##518） */
export interface LaunchInstance {
    readonly pid: number;
    /** 注册表里的 launch 名（如 `lab`；slot 已取消，不再有 `lab/2` 这种后缀） */
    readonly launch: string;
    /** 实例自报名字（`DIY_INSTANCE_NAME`）；没写 = 空串 */
    readonly name: string;
    /** 展示名：name 优先，否则 `<app>#<pid>` —— 任何活着的实例都有认得出的名字 */
    readonly displayName: string;
    readonly diyHome: string;
    readonly startedAt: string;
    readonly port: number | null;
}

export interface LaunchStatus {
    /** `(worktree, app, launch)` 的稳定 key（UI 选中 / 定位用） */
    readonly key: string;
    /**
     * 该 worktree 属于哪个 git 仓库（仓库根绝对路径）。
     *
     * 为什么必需：本机同时扫多个仓库（`_diy` 与主仓 `diy` 是两个独立 git 仓，
     * 各自有 worktree），`git worktree list` 只看自己那个 —— 合并后必须保留归属，
     * 否则 UI 里两个仓库的分支会混进同一张表，无法辨认。
     */
    readonly repo: string;
    readonly worktree: string;
    /** worktree 的展示形式（路径 + 分支，右侧面板用） */
    readonly worktreeLabel: string;
    /** worktree 路径的展示形式（左侧树只放这一行） */
    readonly worktreePath: string;
    readonly branch: string | null;
    readonly app: string;
    readonly appTitle: string;
    readonly launch: string;
    readonly launchTitle: string;
    readonly command: string;
    /** app.yaml 里声明的 env（详情页「环境变量」） */
    readonly env: Readonly<Record<string, string>>;
    /** app 目录（命令在这儿执行；路径打开也用它） */
    readonly appDir: string;
    /** app.yaml 路径（详情页可打开） */
    readonly yamlPath: string;
    /** 数据根（绝对路径；app.yaml 的 home 相对 worktree 解析） */
    readonly home: string;
    /** app.yaml 里是否显式声明了 `home`（没声明 = 配置错误，见 configIssues） */
    readonly homeDeclared: boolean;
    /** 该 launch 的配置问题（空数组 = 正常） */
    readonly configIssues: readonly LaunchConfigIssue[];
    /** 数据根的 instance-id；从未启动过 = null */
    readonly nodeId: string | null;
    /** `diy://<nodeId>/<app>.<launch>`；nodeId 缺席 = null */
    readonly uri: string | null;
    /** 该 worktree 是否构建过（存在 `build/`）；未构建 = 条目标灰 + 给「构建」按钮 */
    readonly built: boolean;
    readonly running: boolean;
    /** 已拉起但还没写注册表（构建 / 启动中） */
    readonly starting: boolean;
    readonly entries: readonly EntryStatus[];
    /** 该 launch 的**所有**在跑实例（##518：同一入口可起多份 `lab/1`、`lab/2`）；空 = 未启动 */
    readonly instances: readonly LaunchInstance[];
    /** 最近启动的那一份（兼容旧字段：`runtime !== null` ≡ 至少一份在跑） */
    readonly runtime: LaunchRuntime | null;
}

/**
 * 没被任何 worktree launch 认领的实例（典型：全局 `diy` 起的**真生产实例**，数据根 `~/.diy`）。
 *
 * 为什么要单列：这类实例的 `(worktree, app, launch)` 可能与某个 worktree 的 launch 撞上，
 * 但数据根完全不同 —— 它既不是那条 launch 在跑，也**绝不能**被面板上的「停止」误杀。
 * 匹配键因此必须带数据根（见 matchRecord 的 expectedHome）。
 */
export interface ExternalInstance {
    readonly pid: number;
    readonly app: string | null;
    readonly launch: string | null;
    readonly diyHome: string;
    readonly worktree: string | null;
    readonly startedAt: string;
    readonly port: number | null;
    /** 数据根是不是**真正的生产根**（`~/.diy`）：是 ⇒ 只读，不可停止 */
    readonly production: boolean;
}

export interface DevSnapshot {
    readonly repoRoot: string;
    /** 仓库名（主 worktree 目录名），左侧树第一层 */
    readonly repoName: string;
    /** 主 worktree 的分支（第一个 worktree；detached = null） */
    readonly repoBranch: string | null;
    readonly registryDir: string;
    readonly worktreeCount: number;
    readonly appCount: number;
    readonly runningCount: number;
    /** 解析 app.yaml 时遇到的问题（坏 YAML / 缺字段），显示在顶部提示里 */
    readonly problems: readonly string[];
    /** 不属于任何 worktree launch 的实例（真生产 / 手工起的孤儿），只展示不接管 */
    readonly externals: readonly ExternalInstance[];
    /**
     * **按 worktree 归拢的动态实例**（##518）：key = worktree 绝对路径。
     *
     * 与 `launches[].instances` 的区别：那里要求 launch 也对得上，这里**只要 worktree 相同**就挂上 ——
     * 于是「这个工作区此刻跑着什么」一眼可见，包括手工起的、launch 名对不上的那些。
     * 纯展示归属，不写盘、不参与身份判定；没源的工作区（空数组 = 没跑东西）。
     */
    readonly worktreeInstances: Readonly<Record<string, readonly LaunchInstance[]>>;
    readonly launches: readonly LaunchStatus[];
}

/** 构建 / 检查命令的输出会话（单条：同一时刻只跑一个） */
export interface CommandSession {
    readonly id: number;
    readonly key: string;
    readonly command: string;
    readonly commandLine: string;
    readonly running: boolean;
    readonly startedAt: string;
    readonly lines: readonly string[];
}

/** 主进程方法名（renderer 与主进程各写一遍字符串 = 迟早拼错；统一放这里） */
export const DEV_METHODS = {
    snapshot: "snapshot",
    start: "start",
    stop: "stop",
    focus: "focus",
    open: "open",
    run: "run",
    session: "session",
    clearSession: "clearSession",
    revealCdp: "revealCdp",
} as const;

// ── 仓库页（##518：像 VS Code 那样浏览 git 仓库） ────────────

export const REPO_METHODS = {
    overview: "repoOverview",
} as const;

/** 一个 worktree 的 git 状态 */
export interface WorktreeStatus {
    readonly path: string;
    readonly name: string;
    /** 分支短名；detached = null */
    readonly branch: string | null;
    /** 是否是主工作树（`git worktree list` 的第一条） */
    readonly main: boolean;
    /** `git status --porcelain` 的行（最多 200 条，够看；超了给 truncated） */
    readonly changes: readonly string[];
    readonly truncated: boolean;
    /** 相对 upstream 领先/落后；没有 upstream = null */
    readonly ahead: number | null;
    readonly behind: number | null;
    /** 最近一次提交：`<短 sha> <标题>`；读不到 = null */
    readonly head: string | null;
}

/** 一个 git 仓库（主工作树 + 它的 worktree） */
export interface RepoStatus {
    /** 仓库根（主工作树路径） */
    readonly root: string;
    readonly name: string;
    readonly worktrees: readonly WorktreeStatus[];
}

export interface RepoOverview {
    readonly repos: readonly RepoStatus[];
}

// ── 外部仓库（##510：dev-ref 的 UI 面） ──────────────────────

/** 一条已注册的 source（diy.yaml）的对齐结果 */
export interface RefRepo {
    /** host/owner/repo 去重键 */
    readonly key: string;
    /** 完整 source 串（含版本，如 https://github.com/org/repo@v1.0.0） */
    readonly url: string;
    /** @ 后版本段；null = 按 main（分支类 sync 时 pull） */
    readonly version: string | null;
    /** 镜像目录（绝对路径） */
    readonly dir: string;
    /** 本地镜像是否存在（false = 还没 clone，待同步） */
    readonly exists: boolean;
    /** 最后一次 sync 时间（ISO）；null = 从未同步 */
    readonly lastSync: string | null;
    /** 本地落后多少个提交（未 clone / tag 固定 / 无 upstream ⇒ null） */
    readonly behind: number | null;
}

/** 「外部仓库」页的开头：作用域 + 镜像根 + 全部 source */
export interface RefOverview {
    /** 作用域目录（diy.yaml 所在；dev app 传仓库根） */
    readonly root: string;
    /** 镜像根（`$DIY_HOME/ref`） */
    readonly home: string;
    readonly repos: readonly RefRepo[];
}

/** sync 汇总（与 ref.sync 尾帧的 summary 同形） */
export interface RefSyncSummary {
    readonly synced: number;
    readonly tagSkipped: number;
    readonly total: number;
    readonly errors: readonly { readonly spec: string; readonly message: string }[];
}

/** sync 的进度快照：UI 轮询它（page:invoke 是 unary，逐条进度落在这里） */
export interface RefSyncState {
    readonly running: boolean;
    readonly lines: readonly string[];
    readonly summary: RefSyncSummary | null;
    readonly error: string | null;
}

/** 「外部仓库」页的主进程方法名（renderer 与本文件各写一遍字符串 = 迟早拼错） */
export const REF_METHODS = {
    overview: "overview",
    add: "add",
    remove: "remove",
    sync: "sync",
    syncState: "syncState",
    open: "open",
} as const;

/** 允许在 app 目录里执行的命令（白名单：拒绝任意命令注入） */
export const BUILD_COMMANDS = ["build", "check", "test", "sync", "build-pkgs", "clean"] as const;
export type BuildCommand = (typeof BUILD_COMMANDS)[number];

export function isBuildCommand(value: unknown): value is BuildCommand {
    return typeof value === "string" && (BUILD_COMMANDS as readonly string[]).includes(value);
}

/** 路径打开方式 */
export type OpenMode = "finder" | "editor" | "terminal";
export function isOpenMode(value: unknown): value is OpenMode {
    return value === "finder" || value === "editor" || value === "terminal";
}

/** 一个 launch 的三元组身份（跨 IPC 传它，别传下标） */
export interface LaunchRef {
    readonly worktree: string;
    readonly app: string;
    readonly launch: string;
}
