"""配置（.env 前缀 FISHLIB_）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LibConfig(BaseModel):
    fishlib_enabled: bool = Field(default=True, description="总开关")
    fishlib_root: str = Field(default="", description="图库根目录；留空 = <cwd>/data/fishlib")
    fishlib_page: int = Field(default=8, description="每页几张")
    fishlib_dhash_dist: int = Field(default=6, description="dHash 汉明距离 ≤ 这个值就算重复（0~64）")
    fishlib_skin_thresh: float = Field(
        default=0.28, description="肤色像素占比超过这个值 → 粗判为「露」（0~1，只是粗筛）")
    fishlib_vision: bool = Field(default=False, description="是否启用 Vision 二次校验（需要自己接模型）")
    fishlib_max_mb: float = Field(default=8.0, description="单张图大小上限（MB）")
