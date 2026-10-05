"""Shared QLoRA building blocks (4-bit base, LoRA config, tokenizer, dataset
loading) for the SFT and DPO trainers. The heavy training stack imports
lazily inside these functions.
"""
from cli import config

ADAPTERS = config.data_dir() / "adapters"


def _hp() -> dict:
    return config.settings().get("train", {})


def base_model_id() -> str:
    return _hp().get("base_model", "Qwen/Qwen3-32B")


def bnb_config():
    import torch
    from transformers import BitsAndBytesConfig
    if not _hp().get("load_in_4bit", True):
        return None
    return BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
    )


def lora_config():
    from peft import LoraConfig
    hp = _hp()
    modules = hp.get("target_modules", "all-linear")
    return LoraConfig(
        r=int(hp.get("lora_r", 16)),
        lora_alpha=int(hp.get("lora_alpha", 32)),
        lora_dropout=float(hp.get("lora_dropout", 0.05)),
        target_modules=modules,
        bias="none",
        task_type="CAUSAL_LM",
    )


class _ChatTemplateNoThinking:
    """Wraps a tokenizer's chat-template call, remembering the original so it can
    still be reached after `apply_chat_template` is replaced on the instance."""

    def __init__(self, original):
        self.original = original

    def __call__(self, *args, **kwargs):
        kwargs.setdefault("enable_thinking", False)
        return self.original(*args, **kwargs)


def _force_no_thinking(tok):
    """Default every chat-template render to Qwen3 reasoning OFF.

    Production serves the adapter with `enable_thinking: False` (kopi-editor
    cloud/serve_vllm.py). trl applies the template internally during training and
    eval applies it at generation; routing both through this one tokenizer means
    the adapter is fit, scored, and served under the *exact* same prompt shape:
    no train/serve skew, no `<think>` blocks leaking into edits. A caller may still
    pass enable_thinking explicitly; this only sets the default.
    """
    tok.apply_chat_template = _ChatTemplateNoThinking(tok.apply_chat_template)
    return tok


def load_tokenizer():
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(base_model_id())
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    return _force_no_thinking(tok)


def load_base_model():
    """The frozen base, 4-bit, for training adapters on top.

    `device_map={"": 0}` forces all weights onto GPU 0, the canonical QLoRA
    pattern for single-GPU training. `device_map="auto"` can leave shards on
    meta/CPU and trip Trainer with "can't train a model loaded with auto".
    """
    import torch
    from transformers import AutoModelForCausalLM
    return AutoModelForCausalLM.from_pretrained(
        base_model_id(),
        quantization_config=bnb_config(),
        torch_dtype=torch.bfloat16,
        device_map={"": 0},
    )


def prepare_for_kbit_training(model):
    """Ready a 4-bit base for QLoRA: enable gradient checkpointing + input grads.

    Required whenever we attach an *already-trained* adapter (DPO) so trl's own
    peft path doesn't run: without this the input embeddings stay frozen and
    gradients never flow back through the checkpointed layers. SFT gets the same
    treatment from trl because it receives the raw base + peft_config.
    """
    from peft import prepare_model_for_kbit_training
    return prepare_model_for_kbit_training(
        model,
        use_gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
    )


def dataset(rel: str):
    from datasets import load_dataset
    path = config.data_dir() / "out" / rel
    if not path.exists():
        raise SystemExit(f"missing {path}, run `build` to assemble datasets first.")
    return load_dataset("json", data_files=str(path), split="train")


def merge(adapter_dir, out_dir) -> None:
    """Fold an adapter into the base weights for a single served model (vLLM).

    Loads the base at bf16 (not 4-bit) so the merge is lossless; needs enough VRAM
    for the full-precision base (learning.md §3.3).
    """
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM

    from cli import ui

    ui.step(f"merging adapter -> {out_dir}")
    base = AutoModelForCausalLM.from_pretrained(
        base_model_id(), torch_dtype=torch.bfloat16, device_map="auto")
    model = PeftModel.from_pretrained(base, str(adapter_dir))
    model = model.merge_and_unload()
    model.save_pretrained(str(out_dir))
    load_tokenizer().save_pretrained(str(out_dir))
    ui.ok(f"merged model written to {out_dir}, serve with vLLM (gcloud-model-serving.md)")
