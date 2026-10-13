"""task-32 验收条款 6：证明新用例**真能证伪**，且不碰生产文件。

做法：把整个 `brain/agentfarm` 包复制到 `scratch/_t32_mut/agentfarm`，只在**副本**上按名字注入
一处错误判断；跑目标用例时应变红。生产 `brain/` 全程只读（最后用 SHA256 证明没变）。

用法：
    python scratch/_t32_mutate.py                      # 只复制（对照组）
    python scratch/_t32_mutate.py m32a_no_plot_whitelisted
    python scratch/_t32_mutate.py m32b_cap_returns_none
    python scratch/_t32_mutate.py m32c_no_work_spot
"""

import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "brain" / "agentfarm"
DST = ROOT / "scratch" / "_t32_mut" / "agentfarm"

MUTS = {
    # ① 把 no_plot 加回白名单 ⇒ "no_plot 永远不是正当理由"这条必须红
    "m32a_no_plot_whitelisted": [
        ('JUSTIFIED_END_REASONS = ("night", "stamina", "no_work")',
         'JUSTIFIED_END_REASONS = ("night", "stamina", "no_work", "no_plot")  # MUT32a'),
    ],
    # ② 软上限改回旧行为（触顶直接 return None）⇒ "触顶但区内有活仍要干完"必须红
    "m32b_cap_returns_none": [
        ('            if self.plots_today >= self.max_plots_per_day:\n'
         '                self.plot = cand\n'
         '                self.zone_name = str(cand.get("zone") or "")\n'
         '                if not self.plots_capped_noted:\n'
         '                    note = (f"已开满 {self.plots_today} 片地（上限 {self.max_plots_per_day}），"\n'
         '                            f"不再累计新作业区：直接在有活的「{self.zone_name or \'窗口\'}」继续做")\n'
         '                    self.plots_capped_noted = True\n'
         '                    rep.notes.append(note)\n'
         '                    self._journal("plots_capped", plots_today=self.plots_today,\n'
         '                                  limit=self.max_plots_per_day, zone=self.zone_name,\n'
         '                                  tiles=len(cand["tiles"]), note=note)\n'
         '                return self.plot\n',
         '            if self.plots_today >= self.max_plots_per_day:  # MUT32b 旧行为：直接憋停\n'
         '                rep.notes.append(f"今天已经开了 {self.plots_today} 片地，不再换区")\n'
         '                return self.plot if (self.plot and self._plot_has_work(obs, self.plot["tiles"])) else None\n'),
    ],
    # ③ 掐掉"活所在的格子"兜底 ⇒ "不许 no_plot 收工、要把水浇掉"必须红
    "m32c_no_work_spot": [
        ('        tmap = FarmWorker.tiles_of(obs)\n'
         '        tiles = [t for t, v in tmap.items()\n'
         '                 if v.get("crop") and (not v.get("watered") or v.get("ripe"))]\n',
         '        tmap = FarmWorker.tiles_of(obs)\n'
         '        tiles = []  # MUT32c 兜底失效\n'),
    ],
}


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    if name and name not in MUTS:
        print(f"未知变异名 {name!r}；可选 {sorted(MUTS)}")
        return 2

    if DST.exists():
        shutil.rmtree(DST)
    DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SRC, DST)

    if not name:
        print(f"已复制生产包到 {DST}（对照组，未注入）")
        return 0

    target = DST / "longrun.py"
    text = target.read_text(encoding="utf-8")
    for old, new in MUTS[name]:
        n = text.count(old)
        if n != 1:
            print(f"❌ 模式出现 {n} 次（要求恰好 1 次），拒绝注入：{old[:120]!r}")
            return 2
        text = text.replace(old, new)
    target.write_text(text, encoding="utf-8")
    print(f"✅ 已在副本注入 {name}：{target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
