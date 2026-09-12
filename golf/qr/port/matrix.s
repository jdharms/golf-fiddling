; The module matrix: copy, walk, and the nametable it becomes.
;
; The ROM table is a 38x38 grid (37 modules plus a row and column of zero
; padding) with the mask baked into the free cells: $FE and $FF are free, and
; bit 0 is the mask bit. So placing a bit is `cell & 1` xor the data bit, and
; there is no mask predicate anywhere on cart.

QrRight       = QrTemp + 0          ; right column of the pair being walked
QrUpward      = QrTemp + 1          ; 0 = walking up, non-zero = down
QrRowsLeft    = QrTemp + 2
QrBitIndex    = QrTemp + 3          ; code word index of the next bit
QrBitMask     = QrTemp + 4          ; bit within that code word
QrBitValue    = QrTemp + 5
QrCellMask    = QrTemp + 6          ; the mask bit of the cell being placed
QrNtTile      = QrTemp + 7          ; tile column, 0..18
QrNtCol       = QrTemp + 8          ; module column, 0..36 step 2
QrNtRows      = QrTemp + 9
QrNtAcc       = QrTemp + 10

QrMatrixLastRow = QrMatrixRowOffset36
QrMatrixRow1 = QrMatrix + QrMatrixStride

; --------------------------------------------------------------------------
; Copy the static matrix into RAM.
; --------------------------------------------------------------------------

QrCopyMatrix:
        lda #<QrStaticMatrix
        sta PtrA
        lda #>QrStaticMatrix
        sta PtrA + 1
        lda #<QrMatrix
        sta PtrB
        lda #>QrMatrix
        sta PtrB + 1

        ldx #QrMatrixPages
        ldy #0
@page:
        lda (PtrA),y
        sta (PtrB),y
        iny
        bne @page
        inc PtrA + 1
        inc PtrB + 1
        dex
        bne @page

        ldy #0
@tail:
        lda (PtrA),y
        sta (PtrB),y
        iny
        cpy #QrMatrixTail
        bne @tail
        rts

; --------------------------------------------------------------------------
; The next data bit, in A, as 0 or 1. Y is preserved: the caller is holding it
; as the column offset into the current row.
;
; Past the end of the code word stream the bits are zero — the seven remainder
; bits version 5 has spare — and the cursor is allowed to run on harmlessly.
; --------------------------------------------------------------------------

QrNextBit:
        lda #0
        sta QrBitValue
        ldx QrBitIndex
        cpx #QrTotalCodewords
        bcs @advance
        lda QrInterleaved,x
        and QrBitMask
        beq @advance
        lda #1
        sta QrBitValue
@advance:
        lsr QrBitMask
        bne @done
        lda #$80
        sta QrBitMask
        inc QrBitIndex
@done:
        lda QrBitValue
        rts

; --------------------------------------------------------------------------
; Place one module: Y is 1 for the right column of the pair, 0 for the left.
; Fixed modules are left alone.
; --------------------------------------------------------------------------

QrPlaceCell:
        lda (PtrC),y
        cmp #$FE
        bcc @fixed
        and #$01
        sta QrCellMask
        jsr QrNextBit
        eor QrCellMask
        sta (PtrC),y
@fixed:
        rts

; --------------------------------------------------------------------------
; Walk the data region: column pairs right to left, skipping the vertical
; timing pattern, alternating upward and downward, right column before left.
; --------------------------------------------------------------------------

QrWalkMatrix:
        lda #0
        sta QrBitIndex
        lda #$80
        sta QrBitMask
        lda #QrModuleSize - 1
        sta QrRight

@column:
        lda QrRight
        cmp #6                          ; the timing column is never a pair
        bne @direction
        lda #5
        sta QrRight
@direction:
        lda QrRight
        clc
        adc #1
        and #$02
        sta QrUpward

        lda QrRight                     ; PtrC = QrMatrix + row * 38 + right - 1
        sec
        sbc #1
        clc
        adc #<QrMatrix
        sta PtrC
        lda #>QrMatrix
        adc #0
        sta PtrC + 1
        lda QrUpward
        bne @rows                       ; downward starts at row 0
        lda PtrC
        clc
        adc #<QrMatrixLastRow
        sta PtrC
        lda PtrC + 1
        adc #>QrMatrixLastRow
        sta PtrC + 1

@rows:
        lda #QrModuleSize
        sta QrRowsLeft
@row:
        ldy #1
        jsr QrPlaceCell
        ldy #0
        jsr QrPlaceCell

        lda QrUpward
        bne @down
        lda PtrC
        sec
        sbc #QrMatrixStride
        sta PtrC
        lda PtrC + 1
        sbc #0
        sta PtrC + 1
        jmp @stepped
@down:
        lda PtrC
        clc
        adc #QrMatrixStride
        sta PtrC
        lda PtrC + 1
        adc #0
        sta PtrC + 1
@stepped:
        dec QrRowsLeft
        bne @row

        lda QrRight
        sec
        sbc #2
        sta QrRight
        bpl @column
        rts

; --------------------------------------------------------------------------
; The 19x19 nametable. Four modules per tile, and the padding row and column
; are what let the last tile of each axis be read without a bounds test.
; --------------------------------------------------------------------------

QrBuildNametable:
        lda #<QrMatrix
        sta PtrA
        lda #>QrMatrix
        sta PtrA + 1
        lda #<QrMatrixRow1
        sta PtrB
        lda #>QrMatrixRow1
        sta PtrB + 1
        lda #<QrNametable
        sta PtrD
        lda #>QrNametable
        sta PtrD + 1

        lda #QrTileCount
        sta QrNtRows
@row:
        lda #0
        sta QrNtTile
        sta QrNtCol
@tile:
        ldy QrNtCol
        lda (PtrA),y                    ; top left
        and #$01
        asl a
        sta QrNtAcc
        iny
        lda (PtrA),y                    ; top right
        and #$01
        ora QrNtAcc
        asl a
        sta QrNtAcc
        ldy QrNtCol
        lda (PtrB),y                    ; bottom left
        and #$01
        ora QrNtAcc
        asl a
        sta QrNtAcc
        iny
        lda (PtrB),y                    ; bottom right
        and #$01
        ora QrNtAcc
        clc
        adc #QrTileBase
        ldy QrNtTile
        sta (PtrD),y

        inc QrNtTile
        lda QrNtCol
        clc
        adc #2
        sta QrNtCol
        ldy QrNtTile
        cpy #QrTileCount
        bne @tile

        lda PtrA                        ; down two module rows
        clc
        adc #QrMatrixStride + QrMatrixStride
        sta PtrA
        lda PtrA + 1
        adc #0
        sta PtrA + 1
        lda PtrB
        clc
        adc #QrMatrixStride + QrMatrixStride
        sta PtrB
        lda PtrB + 1
        adc #0
        sta PtrB + 1

        lda PtrD                        ; and one nametable row
        clc
        adc #QrTileCount
        sta PtrD
        lda PtrD + 1
        adc #0
        sta PtrD + 1

        dec QrNtRows
        bne @row
        rts
