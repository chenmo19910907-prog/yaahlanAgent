# MOA-generative · Usage（英文摘要）

完整中文能力清单与命令见 **[使用方法.md](./使用方法.md)**（由 `config/registry.json` 自动生成）。

## When to use

- Endpoint exists as client HTTP; want to replay via MSE / local `moa_execute`
- No ready-made `MOA/templates/` backdoor template
- You already have Tunnel request body and ServiceUrl from the call chain

## Recommended command

```bash
python3 workflow/workflow_execute.py run moa-generative-run \
  --service-url <ServiceUrl> \
  --method <Method> \
  --body-file <capture-body.json>
```

Defaults: `--timeout-ms 20000`, `--strict 0` (proxy OK even if business rejects).

## Packing rules (critical)

| Field | Value |
|------|--------|
| `type` | `"moa"` |
| `url` | Call-chain ServiceUrl |
| `method` | Call-chain Method (e.g. `signIn`, not `signin`) |
| `header` | Full capture body as a **JSON string** |
| `params[0].type` | `"json"` |
| `params[0].value` | The **same** body object |

Do not guess ServiceUrl from HTTP path alone. Verified mappings: [mappings.md](./mappings.md).
