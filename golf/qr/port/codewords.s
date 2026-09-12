; Data code words, error correction, and the interleave.
;
; The stages here run one after another and share QrTemp; nothing is held
; across a stage boundary.

QrCwCarry     = QrTemp + 0          ; nibble carried between code words
QrRsData      = QrTemp + 1          ; running index into the data code words
QrRsOut       = QrTemp + 2          ; running index into the EC code words
QrRsBlocks    = QrTemp + 3          ; blocks left
QrRsCount     = QrTemp + 4          ; data bytes left in this block
QrRsFactor    = QrTemp + 5          ; feedback term
QrRsLogFactor = QrTemp + 6          ; its log

; --------------------------------------------------------------------------
; The 86 data code words.
;
; The 12-bit header (4-bit mode, 8-bit count) puts every URL character on a
; nibble boundary, so this is a nibble shift rather than a bit packer. Code
; words 0-27 never vary — prefix plus the always-`A` first base64 character —
; and come straight out of ROM.
; --------------------------------------------------------------------------

QrBuildCodewords:
        ldx #0
@head:
        lda QrCodewordHead,x
        sta QrDataCodewords,x
        inx
        cpx #QrConstantCodewords
        bne @head

@body:                                  ; cw[k] = url[k-2] low nibble : url[k-1] high
        txa
        sec
        sbc #2
        tay
        lda QrUrl,y
        and #$0F
        asl a
        asl a
        asl a
        asl a
        sta QrCwCarry
        iny
        lda QrUrl,y
        lsr a
        lsr a
        lsr a
        lsr a
        ora QrCwCarry
        sta QrDataCodewords,x
        inx
        cpx #QrUrlLen + 1
        bne @body

        lda QrUrl + QrUrlLen - 1        ; the last character's low nibble, then
        and #$0F                        ; the 4-bit terminator
        asl a
        asl a
        asl a
        asl a
        sta QrDataCodewords,x
        inx

        ldy #0                          ; pad alternately $EC $11
@pad:
        lda QrPadCodewords,y
        sta QrDataCodewords,x
        tya
        eor #$01
        tay
        inx
        cpx #QrDataCodewordCount
        bne @pad
        rts

QrPadCodewords:
        .byte $EC, $11

; --------------------------------------------------------------------------
; Reed-Solomon, two blocks of 43 data code words to 24 EC code words each.
;
; The LFSR form: take the feedback term, shift the remainder down, and xor in
; the generator polynomial scaled by that term. Scaling is done in the log
; domain, so the 256-entry antilog table needs the sum folded back by 255 — one
; `adc #0` under a set carry.
; --------------------------------------------------------------------------

QrReedSolomon:
        lda #0
        sta QrRsData
        sta QrRsOut
        lda #2
        sta QrRsBlocks

@block:
        lda #0
        ldx #0
@clear:
        sta QrRsRemainder,x
        inx
        cpx #QrEcPerBlock
        bne @clear

        lda #QrDataPerBlock
        sta QrRsCount

@byte:
        ldx QrRsData
        lda QrDataCodewords,x
        eor QrRsRemainder
        sta QrRsFactor
        inc QrRsData

        ldx #0                          ; remainder <<= 1 byte
@shift:
        lda QrRsRemainder + 1,x
        sta QrRsRemainder,x
        inx
        cpx #QrEcPerBlock - 1
        bne @shift
        lda #0
        sta QrRsRemainder + QrEcPerBlock - 1

        lda QrRsFactor
        beq @next                       ; a zero term scales everything to zero
        tay
        lda QrLogTable,y
        sta QrRsLogFactor
        ldx #0
@mix:
        ldy QrGeneratorPoly + 1,x       ; byte 0 is the leading 1
        lda QrLogTable,y
        clc
        adc QrRsLogFactor
        bcc @noWrap
        adc #0                          ; carry is set: -256 + 1 = -255
@noWrap:
        tay
        lda QrAntilogTable,y
        eor QrRsRemainder,x
        sta QrRsRemainder,x
        inx
        cpx #QrEcPerBlock
        bne @mix

@next:
        dec QrRsCount
        bne @byte

        ldx #0                          ; remainder is this block's EC
@out:
        lda QrRsRemainder,x
        ldy QrRsOut
        sta QrEcCodewords,y
        inc QrRsOut
        inx
        cpx #QrEcPerBlock
        bne @out

        dec QrRsBlocks
        bne @block
        rts

; --------------------------------------------------------------------------
; Interleave. Both blocks are the same length in version 5-M, so this is a
; plain alternating copy with no ragged-block handling.
; --------------------------------------------------------------------------

QrInterleaveCodewords:
        ldx #0
        ldy #0
@data:
        lda QrDataCodewords,x
        sta QrInterleaved,y
        iny
        lda QrDataCodewords + QrDataPerBlock,x
        sta QrInterleaved,y
        iny
        inx
        cpx #QrDataPerBlock
        bne @data

        ldx #0
@ec:
        lda QrEcCodewords,x
        sta QrInterleaved,y
        iny
        lda QrEcCodewords + QrEcPerBlock,x
        sta QrInterleaved,y
        iny
        inx
        cpx #QrEcPerBlock
        bne @ec
        rts
