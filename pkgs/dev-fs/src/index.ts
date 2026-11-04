// index.ts — dev-fs 公共入口：API（schema）+ 实现（jail / 三个方法）+ 绑定函数

export { fsApi, FsEntry, ReadOutput, type FsEntryValue } from "./api.js";
export { jail, listDir, readText, writeText, bindFsHandlers } from "./impl.js";
