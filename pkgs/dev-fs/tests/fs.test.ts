/**
 * fs.test.ts — jail 与三个方法的单测（tmpdir，不碰真实仓库）
 */
import { describe, expect, it, beforeEach, afterEach } from "vitest";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { jail, listDir, readText, writeText } from "../src/impl.js";

let root: string;
beforeEach(() => {
    root = mkdtempSync(join(tmpdir(), "dev-fs-"));
    mkdirSync(join(root, ".git")); // 冒充 worktree（jail 只判存在性）
    mkdirSync(join(root, "src"));
    writeFileSync(join(root, "src", "a.ts"), "export const a = 1;\n");
    writeFileSync(join(root, "README.md"), "# hi\n");
});
afterEach(() => rmSync(root, { recursive: true, force: true }));

describe("jail", () => {
    it("接受相对路径；越界 / 绝对路径 / 非 worktree 都拒", () => {
        expect(jail(root, "src/a.ts")).toBe(join(root, "src", "a.ts"));
        expect(jail(root, "")).toBe(root);
        expect(() => jail(root, "../x")).toThrow(/越界/);
        expect(() => jail(root, "/etc/passwd")).toThrow(/相对/);
        expect(() => jail(tmpdir(), "x")).toThrow(/不是 git worktree/);
    });
});

describe("listDir / readText / writeText", () => {
    it("目录在前；文件带大小", () => {
        const entries = listDir(root, "");
        expect(entries.map((e) => `${e.kind}:${e.name}`)).toEqual(["dir:src", "file:README.md"]);
        expect(entries[0]?.size).toBeNull();
        expect(entries[1]?.size).toBe(5);
        expect(listDir(root, "src").map((e) => e.path)).toEqual(["src/a.ts"]);
    });

    it("读写往返；二进制只回标记", () => {
        const got = readText(root, "src/a.ts");
        expect(got.text).toBe("export const a = 1;\n");
        expect(got.binary).toBe(false);
        writeText(root, "src/a.ts", "changed\n");
        expect(readText(root, "src/a.ts").text).toBe("changed\n");

        writeFileSync(join(root, "blob.bin"), Buffer.from([0, 1, 2]));
        expect(readText(root, "blob.bin")).toMatchObject({ binary: true, text: "" });
    });

    it("读目录 / 写不存在的子目录都报错（不静默造目录）", () => {
        expect(() => readText(root, "src")).toThrow(/目录/);
        expect(() => writeText(root, "nope/x.ts", "x")).toThrow(/目录不存在/);
    });
});
