# Vendored NInfer artifact tooling

`tools/artifact/` と `tools/convert/` は `kaushikvira/ninfer`
（commit 2caeb40、2026-09-17時点）から Vendoring した DFlash2 graft ツール一式。

- 出所: https://github.com/kaushikvira/ninfer (tools/artifact, tools/convert)
- 用途: V2 `.ninfer` artifact に z-lab/Qwen3.8-27B-DFlash2 モジュールを
  W8G32/BF16 符号化で追加（graft）する CPU 側ツール。RTX 4090 (sm_89) の
  NInfer fork が読む artifact を生成する。
- 変更ポリシー: 上流のバグフィックスは cherry-pick してこのコメントの日付を
  更新する。無関係な上流変更は取り込まない。
- 依存: torch (CPU), safetensors。graft はホスト側の Python 環境から実行する。
  実行前に両パッケージの導入が必要で、サービス用 NInfer イメージには含めない。
