"""task-33 验收条款 6：证明 sleep 用例**真能证伪**，且不碰生产文件。

做法：把整个 `brain/agentfarm` 包复制到 `scratch/_t33_mut/agentfarm`，只在**副本**上按名字
注入一处错误判断；跑目标用例时应变红。生产 `brain/` 全程只读（最后再用 SHA256 证明没变）。

用法：
    python scratch/_t33_mutate.py            # 只复制（对照组）
    python scratch/_t33_mutate.py m1_blind_send
    python scratch/_t33_mutate.py m2_ok_claims_day
    python scratch/_t33_mutate.py m3_uimodal_is_failure
"""

import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "brain" / "agentfarm"
DST = ROOT / "scratch" / "_t33_mut" / "agentfarm"

MUTS = {
    # ① 去掉"没提问就别发请求"的早退 ⇒ 变成盲发 sleep（run2 的病）
    "m1_blind_send": [
        ("        if not ready:\n", "        if False:  # MUT1 盲发 sleep\n"),
    ],
    # ② 正常路径上把"日期真的变了"换成"回执 ok 就算数" ⇒ 回执成了判据
    "m2_ok_claims_day": [
        ("        r.receipt = _receipt_of(res)\n        if day_after != day_before:\n",
         "        r.receipt = _receipt_of(res)\n        if True:  # MUT2 回执 ok 就当跨日\n"),
    ],
    # ③ 把"踩触发格回 ui_modal = 命中信号"改回失败 ⇒ 走不到应答那一步
    "m3_uimodal_is_failure": [
        ('            if status == "ui_modal":\n', '            if False:  # MUT3 ui_modal 当失败\n'),
    ],
    # ---- NIT-3 delta 复核（2026-10-13 晚）----
    # ④ 掐掉"跨日已发生 ⇒ 仍算成功"这条（NIT-3② 的判据）
    "m4_bridgedown_not_success": [
        ("            if day_before is not None and day_after != day_before:\n",
         "            if False:  # MUT4 跨日也不算成功\n"),
    ],
    # ⑤ 掐掉桥码归一（connection_broken ⇒ bridge_down）
    "m5_no_normalize": [
        ('        if status in BRIDGE_DOWN_STATUSES:\n'
         '            status = "bridge_down"                 # 桥自己没了 ⇒ 统一码，别让 run3 只看到 connection_broken\n',
         '        if False:  # MUT5 不归一\n'
         '            status = "bridge_down"\n'),
    ],
    # ⑥ 去掉外层 wrapper 的收口 ⇒ BridgeError 直接穿出（NIT-3 的病本身）
    "m6_no_wrapper": [
        ("        except BridgeError as exc:\n"
         "            return self._sleep_bridge_fail(r, exc, state)\n"
         "        except Exception as exc:                   # noqa: BLE001 - 观测解析等意外同样不许穿出\n"
         '            return self._sleep_bridge_fail(r, exc, state, fallback_status="bridge_down")\n',
         "        except BridgeError as exc:  # MUT6 不收口\n"
         "            raise\n"
         "        except Exception as exc:  # noqa: BLE001\n"
         "            raise\n"),
    ],
    # ⑦ 连观测都拿不到时假装成功（"如实失败"的反面）
    "m7_fake_success": [
        ('        except Exception as exc2:                  # noqa: BLE001 - 连观测都拿不到 ⇒ 只能报桥掉线\n'
         '            diag = f"{diag}；失败后再观测也失败：{type(exc2).__name__}: {exc2}"\n'
         '            r.after = {"day_before": list(day_before) if day_before else None, "stage": stage}\n',
         '        except Exception as exc2:                  # noqa: BLE001 - MUT7 假装成功\n'
         '            r.ok = True\n'
         '            r.reason = "MUT7 假装跨日"\n'
         '            return r\n'),
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

    target = DST / "farmwork.py"
    text = target.read_text(encoding="utf-8")
    for old, new in MUTS[name]:
        n = text.count(old)
        if n != 1:
            print(f"❌ 模式出现 {n} 次（要求恰好 1 次），拒绝注入：{old!r}")
            return 2
        text = text.replace(old, new)
    target.write_text(text, encoding="utf-8")
    print(f"✅ 已在副本注入 {name}：{target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
