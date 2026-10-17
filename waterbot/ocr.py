"""macOS Vision OCR wrapper: 吃 numpy BGR 影像，回傳 [(文字, 中心點x, 中心點y, 信心值)]。

Vision 的座標是左下原點的 0~1 正規化值，這裡一律換成影像的像素座標（左上原點）。
"""
import Vision
import Quartz
import numpy as np
from Foundation import NSData


def _to_cgimage(bgr: np.ndarray):
    rgba = np.ascontiguousarray(
        np.dstack([bgr[:, :, 2], bgr[:, :, 1], bgr[:, :, 0],
                   np.full(bgr.shape[:2], 255, np.uint8)])
    )
    h, w = rgba.shape[:2]
    provider = Quartz.CGDataProviderCreateWithCFData(
        NSData.dataWithBytes_length_(rgba.tobytes(), rgba.nbytes)
    )
    return Quartz.CGImageCreate(
        w, h, 8, 32, w * 4,
        Quartz.CGColorSpaceCreateDeviceRGB(),
        Quartz.kCGImageAlphaNoneSkipLast,
        provider, None, False, Quartz.kCGRenderingIntentDefault,
    )


def ocr(bgr: np.ndarray, langs=("zh-Hant", "zh-Hans", "en-US"), fast=False):
    h, w = bgr.shape[:2]
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(
        Vision.VNRequestTextRecognitionLevelFast if fast
        else Vision.VNRequestTextRecognitionLevelAccurate
    )
    req.setRecognitionLanguages_(list(langs))
    req.setUsesLanguageCorrection_(False)

    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
        _to_cgimage(bgr), None
    )
    ok, err = handler.performRequests_error_([req], None)
    if not ok:
        raise RuntimeError(f"Vision failed: {err}")

    out = []
    for obs in (req.results() or []):
        cand = obs.topCandidates_(1)
        if not cand:
            continue
        box = obs.boundingBox()
        cx = (box.origin.x + box.size.width / 2) * w
        cy = (1.0 - (box.origin.y + box.size.height / 2)) * h  # 翻成左上原點
        out.append((cand[0].string(), int(round(cx)), int(round(cy)),
                    float(cand[0].confidence())))
    return out
