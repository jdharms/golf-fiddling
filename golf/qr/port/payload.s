; The 36-byte payload and the URL it becomes.
;
;   byte  0      protocol version
;   bytes 1-8    seed ID        (patched in at build time)
;   bytes 9-12   player ID      (patched in, one per player slot)
;   byte  13     flags: bits 0-1 player slot
;   bytes 14-31  hole records, strokes-1 in the high nibble, putts in the low
;   bytes 32-35  HalfSipHash-2-4-32 over bytes 0-31
;
; Both fields clamp rather than overflow, which is also what makes an unplayed
; hole safe: the game leaves $FF there, and $FF clamps to 16 strokes like any
; other blow-up. The URL is the 26-byte prefix followed by 48 base64url
; characters, 74 in all.

QrSlot        = QrTemp + 0          ; player slot, 0 or 1
QrStrokeBase  = QrTemp + 1          ; slot * 36
QrPuttBase    = QrTemp + 2          ; slot * 18
QrHoleByte    = QrTemp + 3          ; hole record under construction
QrB64Src      = QrTemp + 4          ; payload index while encoding
QrB64Group    = QrTemp + 5          ; the three bytes of one base64 group
QrB64Tmp      = QrTemp + 8

; --------------------------------------------------------------------------
; Build the payload for the player slot in A, MAC included.
; --------------------------------------------------------------------------

QrBuildPayload:
        and #$03
        sta QrSlot

        lda #$01                        ; protocol version
        sta QrPayload

        ldx #0
@seed:
        lda QrSeedId,x
        sta QrPayload + 1,x
        inx
        cpx #8
        bne @seed

        lda QrSlot                      ; player ID, four bytes per slot
        asl a
        asl a
        tay
        ldx #0
@player:
        lda QrPlayerId,y
        sta QrPayload + 9,x
        iny
        inx
        cpx #4
        bne @player

        lda QrSlot                      ; flags
        sta QrPayload + 13

        lda #0                          ; per-slot array bases
        sta QrStrokeBase
        sta QrPuttBase
        lda QrSlot
        beq @holes
        lda #StrokeStride
        sta QrStrokeBase
        lda #PuttStride
        sta QrPuttBase

@holes:
        ldx #0
@hole:
        txa
        clc
        adc QrStrokeBase
        tay
        lda PerHoleStrokes,y
        cmp #1                          ; clamp 1..16
        bcs @atLeastOne
        lda #1
@atLeastOne:
        cmp #17
        bcc @strokesOk
        lda #16
@strokesOk:
        sec
        sbc #1
        asl a
        asl a
        asl a
        asl a
        sta QrHoleByte

        txa
        clc
        adc QrPuttBase
        tay
        lda PerHolePutts,y
        cmp #16                         ; clamp 0..15
        bcc @puttsOk
        lda #15
@puttsOk:
        ora QrHoleByte
        sta QrPayload + 14,x
        inx
        cpx #18
        bne @hole

        lda QrSlot                      ; the slot's MAC key
        asl a
        asl a
        asl a
        tay
        ldx #0
@key:
        lda QrMacKey,y
        sta QrHashKey,x
        iny
        inx
        cpx #8
        bne @key
        jmp QrHashMac

; --------------------------------------------------------------------------
; Build the URL from the payload: prefix, then 12 base64url groups.
; --------------------------------------------------------------------------

QrBuildUrl:
        ldx #0
@prefix:
        lda QrUrlPrefix,x
        sta QrUrl,x
        inx
        cpx #QrUrlPrefixLen
        bne @prefix

        lda #0
        sta QrB64Src
@group:
        ldy QrB64Src                    ; three payload bytes
        lda QrPayload,y
        sta QrB64Group + 0
        iny
        lda QrPayload,y
        sta QrB64Group + 1
        iny
        lda QrPayload,y
        sta QrB64Group + 2
        iny
        sty QrB64Src

        lda QrB64Group + 0              ; b0 >> 2
        lsr a
        lsr a
        tay
        lda QrBase64Alphabet,y
        sta QrUrl,x
        inx

        lda QrB64Group + 0              ; (b0 & 3) << 4 | b1 >> 4
        and #$03
        asl a
        asl a
        asl a
        asl a
        sta QrB64Tmp
        lda QrB64Group + 1
        lsr a
        lsr a
        lsr a
        lsr a
        ora QrB64Tmp
        tay
        lda QrBase64Alphabet,y
        sta QrUrl,x
        inx

        lda QrB64Group + 1              ; (b1 & 15) << 2 | b2 >> 6
        and #$0F
        asl a
        asl a
        sta QrB64Tmp
        lda QrB64Group + 2
        lsr a
        lsr a
        lsr a
        lsr a
        lsr a
        lsr a
        ora QrB64Tmp
        tay
        lda QrBase64Alphabet,y
        sta QrUrl,x
        inx

        lda QrB64Group + 2              ; b2 & 63
        and #$3F
        tay
        lda QrBase64Alphabet,y
        sta QrUrl,x
        inx

        cpx #QrUrlLen
        bne @group
        rts
