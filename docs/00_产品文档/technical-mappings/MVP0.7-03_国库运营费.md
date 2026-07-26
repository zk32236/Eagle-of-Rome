# MVP0.7-03 — 国库运营费（技术映射）

## 1. 代码目录
```
src/core/service/economic_service.py  # deduct_national_opex()
```

## 2. 核心算法
opex = int(total_conquered_land × land_price_per_unit × national_opex_rate)
默认: land_price=10, rate=0.003

## 3. 版本日志 | v1.0 | 2026-07-12 | 初版 |
