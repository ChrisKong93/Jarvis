import hashlib
import logging
import os
import threading
from typing import List, Optional

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
EMBEDDING_DIMENSION = 384  # all-MiniLM-L6-v2 输出维度
HF_CACHE_DIR = os.path.expanduser("~/.cache/huggingface/hub")


class EmbeddingGenerator:
    def __init__(self, model_name: str = EMBEDDING_MODEL):
        self.model_name = model_name
        self._model = None
        self._fallback_mode = False
        self._download_lock = threading.Lock()
        self._download_started = False

    def _is_model_cached(self) -> bool:
        """检查模型是否已在本地缓存，避免阻塞下载"""
        model_slug = self.model_name.replace("/", "--")
        snapshot_path = os.path.join(HF_CACHE_DIR, f"models--{model_slug}", "snapshots")
        if os.path.isdir(snapshot_path) and os.listdir(snapshot_path):
            return True
        try:
            from huggingface_hub import try_to_load_from_cache
            result = try_to_load_from_cache(self.model_name, "modules.json")
            if result is not None and os.path.isfile(result):
                return True
        except Exception:
            pass
        return False

    def try_download_model_background(self):
        """在后台线程尝试下载模型，不阻塞服务启动。
        下载完成后，后续 embed() 调用自动使用真实模型。
        """
        with self._download_lock:
            if self._download_started:
                return
            self._download_started = True

        if self._is_model_cached():
            logger.info(f"Embedding 模型 {self.model_name} 已在本地缓存")
            return

        def _download():
            try:
                import logging as _logging
                import os as _os

                # HuggingFace Hub 内部重试日志无关紧要，静音掉
                _logging.getLogger("huggingface_hub").setLevel(_logging.CRITICAL)
                _logging.getLogger("sentence_transformers").setLevel(_logging.CRITICAL)
                _logging.getLogger("transformers").setLevel(_logging.CRITICAL)

                _os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "120"
                from sentence_transformers import SentenceTransformer

                logger.info(f"正在后台下载 Embedding 模型 {self.model_name} ...")
                SentenceTransformer(self.model_name)
                logger.info("Embedding 模型下载完成，后续将自动使用真实模型")
            except Exception:
                pass

        thread = threading.Thread(target=_download, daemon=True)
        thread.start()
        logger.info(f"已启动后台模型下载线程 (模型: {self.model_name})")

    def _load_local_model(self):
        if not self._is_model_cached():
            logger.info(
                f"Embedding 模型 {self.model_name} 未在本地缓存，使用 fallback 模式"
            )
            self._fallback_mode = True
            return

        try:
            from sentence_transformers import SentenceTransformer

            logger.info(f"正在加载 Embedding 模型: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
            logger.info("Embedding 模型加载完成")
        except ImportError:
            logger.warning("sentence-transformers 未安装，降级为伪向量模式")
            self._fallback_mode = True
        except Exception as exc:
            logger.warning(f"加载 Embedding 模型失败 ({exc})，降级为伪向量模式")
            self._fallback_mode = True

    def embed(self, text: str) -> List[float]:
        if self._model is None and not self._fallback_mode:
            self._load_local_model()

        if self._fallback_mode or self._model is None:
            return self._fallback_embed(text)

        return self._model.encode(text, show_progress_bar=False).tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if self._model is None and not self._fallback_mode:
            self._load_local_model()

        if self._fallback_mode or self._model is None:
            return [self._fallback_embed(t) for t in texts]

        return self._model.encode(texts, show_progress_bar=False).tolist()

    def _fallback_embed(self, text: str) -> List[float]:
        """当 sentence-transformers 模型不可用时，用字符 n-gram 哈希生成伪向量。
        基于字符 trigram 比单纯关键词哈希有更好的语义区分度。
        """
        vector = [0.0] * EMBEDDING_DIMENSION
        text_lower = text.lower()

        # 字符 trigram 哈希
        seen = set()
        for i in range(len(text_lower) - 2):
            gram = text_lower[i:i + 3]
            if gram in seen:
                continue
            seen.add(gram)
            h = hashlib.md5(gram.encode()).digest()
            for j in range(min(len(h), EMBEDDING_DIMENSION)):
                vector[j] += (h[j] / 255.0) * 2 - 1

        # 单字哈希（补充短文本）
        for ch in text_lower:
            if ch in seen:
                continue
            seen.add(ch)
            h = hashlib.md5(ch.encode()).digest()
            for j in range(min(len(h), EMBEDDING_DIMENSION)):
                vector[j] += (h[j] / 255.0) * 2 - 1

        norm = sum(v * v for v in vector) ** 0.5
        if norm > 0:
            vector = [v / norm for v in vector]
        return vector

    @property
    def dimension(self) -> int:
        return EMBEDDING_DIMENSION


embedding_generator = EmbeddingGenerator()
