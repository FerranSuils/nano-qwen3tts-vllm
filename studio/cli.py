"""Command line for the same studio the web UI and the HTTP API use.

Examples:
  export HF_TOKEN=<YOUR_HUGGINGFACE_TOKEN>
  python -m studio.cli providers
  python -m studio.cli hf-status
  python -m studio.cli set huggingface --model Qwen/Qwen2.5-7B-Instruct
  python -m studio.cli test ollama
  python -m studio.cli design "Mujer de Cádiz, 29 años, risa contenida" --language Spanish
  python -m studio.cli claude-workflow
"""

from __future__ import annotations

import argparse
import json
import sys

from studio import claude_workflow, providers, voices


def _print(payload) -> None:
    json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="studio.cli", description="Voice studio providers, design, and Claude workflow")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("providers", help="List providers without revealing secrets")
    sub.add_parser("hf-status", help="Check HF_TOKEN against the Hugging Face whoami endpoint")

    set_cmd = sub.add_parser("set", help="Save provider settings")
    set_cmd.add_argument("provider")
    set_cmd.add_argument("--api-key", default=None)
    set_cmd.add_argument("--base-url", default=None)
    set_cmd.add_argument("--model", default=None)
    set_cmd.add_argument("--project", default=None)
    set_cmd.add_argument("--location", default=None)
    set_cmd.add_argument("--disable", action="store_true")

    test_cmd = sub.add_parser("test", help="Check that a provider accepts the configured credentials")
    test_cmd.add_argument("provider")

    active = sub.add_parser("use", help="Select the reasoner used when a design call omits provider")
    active.add_argument("provider")

    design = sub.add_parser("design", help="Cast a voice with the active reasoner")
    design.add_argument("brief")
    design.add_argument("--language", default=None)
    design.add_argument("--provider", default=None)
    design.add_argument("--no-save", action="store_true")

    sub.add_parser("voices", help="List builtin and saved voices")
    sub.add_parser("claude-workflow", help="Write .claude agents and skills (requires a Claude key)")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "providers":
            _print(providers.list_public_providers())
        elif args.cmd == "hf-status":
            _print(providers.test_provider("huggingface"))
        elif args.cmd == "set":
            saved = providers.save_provider(
                args.provider,
                {
                    "api_key": args.api_key,
                    "base_url": args.base_url,
                    "model": args.model,
                    "project": args.project,
                    "location": args.location,
                    "enabled": False if args.disable else None,
                },
            )
            if args.provider == "claude" and providers.resolve("claude").api_key:
                saved["workflow"] = claude_workflow.materialize(force=False)
            _print(saved)
        elif args.cmd == "test":
            _print(providers.test_provider(args.provider))
        elif args.cmd == "use":
            _print(providers.set_active_reasoner(args.provider))
        elif args.cmd == "design":
            _print(
                voices.design_voice(
                    args.brief,
                    language=args.language,
                    provider_id=args.provider,
                    save=not args.no_save,
                )
            )
        elif args.cmd == "voices":
            _print({"voices": voices.list_voices()})
        elif args.cmd == "claude-workflow":
            if not providers.resolve("claude").api_key:
                print("Añade ANTHROPIC_API_KEY antes de crear el workflow", file=sys.stderr)
                return 2
            _print(claude_workflow.materialize(force=False))
    except (providers.ProviderError, voices.VoiceError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
