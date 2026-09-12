# Scorecard QR: mask sweep results

> **Note**: Raw output of `golf-qr-validate`, kept so the fixed-mask decision in
> `scorecard_qr.md` can be re-checked without re-running the sweep. Regenerate with
> the commands shown above each table.

## Run 1 — all eight masks

```
golf-qr-validate -n 100 --seed 0
```

Decoders: zxing, opencv. Image: full 256x240 screen.

| mask | native | scale2 | scale3 | aspect | blur_soft | blur_heavy | jpeg_low | rotated | soft_capture | scanlines | combined | overall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 100% | 100% | 100% | 98% | 100% | 100% | 100% | 100% | 100% | 50% | 100% | **95.0%** |
| 1 | 100% | 99% | 99% | 98% | 100% | 100% | 99% | 100% | 99% | 50% | 100% | **94.9%** |
| 2 | 100% | 98% | 98% | 98% | 98% | 100% | 98% | 98% | 100% | 50% | 100% | **94.3%** |
| 3 | 100% | 100% | 100% | 99% | 99% | 100% | 100% | 100% | 99% | 50% | 100% | **94.9%** |
| 4 | 100% | 99% | 99% | 98% | 99% | 100% | 99% | 100% | 100% | 50% | 100% | **94.8%** |
| 5 | 100% | 100% | 100% | 99% | 100% | 100% | 100% | 100% | 100% | 50% | 100% | **95.1%** |
| 6 | 99% | 98% | 98% | 98% | 100% | 100% | 98% | 100% | 100% | 50% | 100% | **94.5%** |
| 7 | 99% | 99% | 99% | 96% | 98% | 99% | 99% | 100% | 100% | 50% | 100% | **94.5%** |

## Spec penalty (lower is better)

| mask | min | mean | max | times spec would pick it |
|---|---|---|---|---|
| 0 | 834 | 1064 | 1300 | 4 |
| 1 | 849 | 1032 | 1237 | 5 |
| 2 | 738 | 907 | 1127 | 51 |
| 3 | 837 | 1038 | 1342 | 4 |
| 4 | 794 | 986 | 1213 | 16 |
| 5 | 845 | 1027 | 1278 | 3 |
| 6 | 786 | 967 | 1193 | 16 |
| 7 | 903 | 1080 | 1366 | 1 |

## 925 failures

| mask | condition | decoder | failures |
|---|---|---|---|
| 0 | scanlines | opencv | 100 |
| 1 | scanlines | opencv | 100 |
| 2 | scanlines | opencv | 100 |
| 3 | scanlines | opencv | 100 |
| 4 | scanlines | opencv | 100 |
| 5 | scanlines | opencv | 100 |
| 6 | scanlines | opencv | 100 |
| 7 | scanlines | opencv | 100 |
| 7 | aspect | opencv | 7 |
| 2 | scale2 | opencv | 5 |
| 2 | scale3 | opencv | 5 |
| 2 | jpeg_low | opencv | 5 |
| 4 | aspect | opencv | 5 |
| 6 | scale2 | opencv | 4 |
| 6 | scale3 | opencv | 4 |
| 6 | jpeg_low | opencv | 4 |
| 0 | aspect | opencv | 3 |
| 1 | aspect | opencv | 3 |
| 2 | rotated | opencv | 3 |
| 2 | blur_soft | opencv | 3 |
| 2 | aspect | opencv | 3 |
| 6 | aspect | opencv | 3 |
| 7 | blur_soft | opencv | 3 |
| 1 | scale2 | opencv | 2 |
| 1 | scale3 | opencv | 2 |
| 1 | jpeg_low | opencv | 2 |
| 1 | soft_capture | opencv | 2 |
| 3 | aspect | opencv | 2 |
| 3 | blur_soft | opencv | 2 |
| 3 | soft_capture | opencv | 2 |
| 4 | blur_soft | opencv | 2 |
| 4 | scale2 | opencv | 2 |
| 4 | scale3 | opencv | 2 |
| 4 | jpeg_low | opencv | 2 |
| 5 | aspect | opencv | 2 |
| 6 | native | opencv | 2 |
| 7 | native | opencv | 2 |
| 7 | scale2 | opencv | 2 |
| 7 | scale3 | opencv | 2 |
| 7 | blur_heavy | opencv | 2 |
| 7 | jpeg_low | opencv | 2 |
| 0 | native | opencv | 1 |
| 0 | scale2 | opencv | 1 |
| 0 | scale3 | opencv | 1 |
| 0 | blur_soft | opencv | 1 |
| 0 | blur_heavy | opencv | 1 |
| 0 | jpeg_low | opencv | 1 |
| 0 | combined | opencv | 1 |
| 0 | rotated | opencv | 1 |
| 1 | native | opencv | 1 |
| 1 | blur_soft | opencv | 1 |
| 2 | combined | opencv | 1 |
| 2 | blur_heavy | opencv | 1 |
| 3 | combined | opencv | 1 |
| 3 | blur_heavy | opencv | 1 |
| 3 | native | opencv | 1 |
| 3 | scale2 | opencv | 1 |
| 3 | scale3 | opencv | 1 |
| 3 | jpeg_low | opencv | 1 |
| 3 | rotated | opencv | 1 |
| 4 | blur_heavy | opencv | 1 |
| 4 | combined | opencv | 1 |
| 5 | scale2 | opencv | 1 |
| 5 | scale3 | opencv | 1 |
| 5 | jpeg_low | opencv | 1 |
| 5 | rotated | opencv | 1 |
| 5 | combined | opencv | 1 |
| 6 | blur_soft | opencv | 1 |
| 6 | soft_capture | opencv | 1 |
| 6 | combined | opencv | 1 |


---

## Run 2 — confirmation on a different seed

```
golf-qr-validate -n 250 --masks 0,2,5 --seed 99
```

Decoders: zxing, opencv. Image: full 256x240 screen.

| mask | native | scale2 | scale3 | aspect | blur_soft | blur_heavy | jpeg_low | rotated | soft_capture | scanlines | combined | overall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 100% | 99% | 99% | 98% | 100% | 100% | 99% | 100% | 100% | 50% | 100% | **94.8%** |
| 2 | 100% | 99% | 99% | 99% | 100% | 100% | 99% | 99% | 100% | 50% | 100% | **94.9%** |
| 5 | 100% | 100% | 100% | 99% | 99% | 99% | 100% | 100% | 99% | 50% | 100% | **95.1%** |

## Spec penalty (lower is better)

| mask | min | mean | max | times spec would pick it |
|---|---|---|---|---|
| 0 | 756 | 1051 | 1315 | 9 |
| 2 | 685 | 908 | 1181 | 113 |
| 5 | 814 | 1034 | 1371 | 12 |

## 838 failures

| mask | condition | decoder | failures |
|---|---|---|---|
| 0 | scanlines | opencv | 250 |
| 2 | scanlines | opencv | 250 |
| 5 | scanlines | opencv | 250 |
| 0 | aspect | opencv | 9 |
| 0 | scale2 | opencv | 6 |
| 0 | scale3 | opencv | 6 |
| 0 | jpeg_low | opencv | 6 |
| 2 | scale2 | opencv | 5 |
| 2 | scale3 | opencv | 5 |
| 2 | jpeg_low | opencv | 5 |
| 5 | blur_soft | opencv | 5 |
| 2 | aspect | opencv | 4 |
| 2 | rotated | opencv | 4 |
| 5 | aspect | opencv | 4 |
| 5 | soft_capture | opencv | 3 |
| 5 | blur_heavy | opencv | 3 |
| 0 | soft_capture | opencv | 2 |
| 0 | native | opencv | 2 |
| 0 | blur_soft | opencv | 2 |
| 2 | blur_heavy | opencv | 2 |
| 2 | native | opencv | 2 |
| 2 | combined | opencv | 2 |
| 5 | native | opencv | 2 |
| 0 | rotated | opencv | 1 |
| 0 | combined | opencv | 1 |
| 0 | blur_heavy | opencv | 1 |
| 2 | blur_soft | opencv | 1 |
| 2 | soft_capture | opencv | 1 |
| 5 | scale2 | opencv | 1 |
| 5 | scale3 | opencv | 1 |
| 5 | jpeg_low | opencv | 1 |
| 5 | combined | opencv | 1 |
