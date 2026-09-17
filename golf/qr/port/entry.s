; The whole pipeline, for one player.
;
; In:  A = player slot, 0 or 1.
; Out: the finished 19x19 nametable at QrNametable, ready for the display layer
;      to upload, and the URL at QrUrl for anything that wants to show it.
;
; Every stage is a separate entry point so the 6502 can be differentially
; tested against the Python oracle one stage at a time, which is what
; `tests/unit/test_qr_port.py` does.

QrBuildCode:
        jsr QrBuildPayload
        jsr QrBuildUrl
        jsr QrBuildCodewords
        jsr QrReedSolomon
        jsr QrInterleaveCodewords
        jsr QrCopyMatrix
        jsr QrWalkMatrix
        jmp QrBuildNametable
