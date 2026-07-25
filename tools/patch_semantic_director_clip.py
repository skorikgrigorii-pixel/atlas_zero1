from pathlib import Path
import shutil
import subprocess
import sys

path = Path("tools/semantic_director_v1.py")
source = path.read_text(encoding="utf-8")

old_image = '''        with torch.no_grad():
            feature = model.get_image_features(
                **inputs
            )

        feature = feature / feature.norm(
            dim=-1,
            keepdim=True,
        )
'''

new_image = '''        with torch.no_grad():
            feature_output = model.get_image_features(
                **inputs
            )

        # Different transformers versions return either a Tensor
        # or a model output object.
        if isinstance(feature_output, torch.Tensor):
            feature = feature_output
        elif hasattr(feature_output, "image_embeds"):
            feature = feature_output.image_embeds
        elif hasattr(feature_output, "pooler_output"):
            feature = feature_output.pooler_output
        elif hasattr(feature_output, "last_hidden_state"):
            feature = feature_output.last_hidden_state[:, 0, :]
        else:
            raise TypeError(
                "Unsupported CLIP image feature output: "
                f"{type(feature_output)!r}"
            )

        feature = feature / feature.norm(
            dim=-1,
            keepdim=True,
        ).clamp(min=1e-12)
'''

old_text = '''        with torch.no_grad():
            features = model.get_text_features(
                **inputs
            )

        features = features / features.norm(
            dim=-1,
            keepdim=True,
        )
'''

new_text = '''        with torch.no_grad():
            feature_output = model.get_text_features(
                **inputs
            )

        # Different transformers versions return either a Tensor
        # or a model output object.
        if isinstance(feature_output, torch.Tensor):
            features = feature_output
        elif hasattr(feature_output, "text_embeds"):
            features = feature_output.text_embeds
        elif hasattr(feature_output, "pooler_output"):
            features = feature_output.pooler_output
        elif hasattr(feature_output, "last_hidden_state"):
            features = feature_output.last_hidden_state[:, 0, :]
        else:
            raise TypeError(
                "Unsupported CLIP text feature output: "
                f"{type(feature_output)!r}"
            )

        features = features / features.norm(
            dim=-1,
            keepdim=True,
        ).clamp(min=1e-12)
'''

image_count = source.count(old_image)
text_count = source.count(old_text)

if image_count != 1:
    raise RuntimeError(
        f"Блок image features найден {image_count} раз вместо одного."
    )

if text_count != 1:
    raise RuntimeError(
        f"Блок text features найден {text_count} раз вместо одного."
    )

updated = source.replace(old_image, new_image, 1)
updated = updated.replace(old_text, new_text, 1)

path.write_text(updated, encoding="utf-8")

result = subprocess.run(
    [sys.executable, "-m", "py_compile", str(path)]
)

if result.returncode != 0:
    shutil.copy2(
        Path(r"tools\\semantic_director_v1.py.backup_clip_output_20260713_134053"),
        path,
    )
    raise RuntimeError(
        "Ошибка синтаксиса. Исходный файл восстановлен."
    )

print("Semantic Director исправлен.")
print("Синтаксис корректен.")
