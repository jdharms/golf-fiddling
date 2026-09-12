; The QR screen: build it, show it, wait to be dismissed.
;
; Every PPU write here happens with rendering off, which is what makes direct
; $2006/$2007 writes safe: the NMI checks the mask shadow ($12) first and, when
; rendering is off, skips the OAM DMA, the PPU update queue and the scroll
; write entirely. Only the music engine runs.
;
; Two colours are enough for the whole screen, so one palette covers it and the
; attribute table is all zeroes. The universal backdrop is white, which makes
; the quiet zone free: the all-light QR tile is the blank tile.

QrDisplaySlot = QrDisplayState + 0      ; player slot being shown
QrHoldCount   = QrDisplayState + 1      ; frames the dismissal gesture has held
QrScreenRows  = QrDisplayState + 2
QrWriteCount  = QrDisplayState + 3
QrPpuLo       = QrDisplayState + 4      ; PPU address of the current row
QrPpuHi       = QrDisplayState + 5

QrBlankTile = QrTileBase                ; QR pattern 0: four light quadrants

; --------------------------------------------------------------------------
; Show every code the round owes: player 1, then player 2 on a two-player
; cart, then back to the caller.
; --------------------------------------------------------------------------

QrShowCodes:
        lda GolfGameMode                ; 18-hole stroke play only
        bne @exit
        lda GameProgress                ; and only a round that finished
        cmp #QrHoleCount
        bcc @exit
        lda #0
        sta QrDisplaySlot
@player:
        lda QrDisplaySlot
        jsr QrBuildCode
        jsr QrDrawScreen
        jsr QrWaitForDismiss
        lda PlayerCount                 ; 0 = one player
        beq @done
        lda QrDisplaySlot
        bne @done
        inc QrDisplaySlot
        jmp @player
@done:
@exit:
        rts

; --------------------------------------------------------------------------
; Draw the whole screen from the nametable QrBuildCode left in RAM.
; --------------------------------------------------------------------------

QrDrawScreen:
        jsr RenderingOff
        jsr HideAllSprites

        jsr LoadCompressedGraphics      ; the card font, for the captions
        .byte CardFontBank, <CardFontTable, >CardFontTable

        jsr QrUploadChr
        jsr QrClearScreen
        jsr QrDrawCode
        jsr QrDrawCaptions
        jsr QrUploadPalette

        lda #QrPpuCtrlValue
        sta PpuCtrlCache
        lda #QrPpuMaskValue
        sta PpuMaskTarget
        lda #0                          ; nametable 0, no scroll
        sta ScrollX
        sta ScrollY
        sta NametableX
        sta NametableY
        jmp RenderingOn

; Set the PPU write address: X high, A low.
QrSetPpuAddr:
        stx PpuAddr2006
        sta PpuAddr2006
        rts

; The 16 QR tiles, straight out of the table blob.
QrUploadChr:
        ldx #>QrChrDest
        lda #<QrChrDest
        jsr QrSetPpuAddr
        ldx #0
@byte:
        lda QrChrTiles,x
        sta PpuData2007
        inx
        bne @byte
        rts

; Blank the whole nametable, then the attribute table. 960 tiles is three
; pages and a 192-byte tail.
QrClearScreen:
        ldx #$20
        lda #$00
        jsr QrSetPpuAddr
        lda #QrBlankTile
        ldx #3
        ldy #0
@page:
        sta PpuData2007
        iny
        bne @page
        dex
        bne @page
        ldy #192
@tail:
        sta PpuData2007
        dey
        bne @tail

        lda #$00                        ; every supertile on palette 0
        ldy #64
@attributes:
        sta PpuData2007
        dey
        bne @attributes
        rts

QrUploadPalette:
        ldx #$3F
        lda #$00
        jsr QrSetPpuAddr
        ldx #0
@byte:
        lda QrPalette,x
        sta PpuData2007
        inx
        cpx #32
        bne @byte
        rts

; The code itself: 19 rows of 19 tiles, one PPU address per row.
QrDrawCode:
        lda #<QrNametable
        sta PtrA
        lda #>QrNametable
        sta PtrA + 1
        lda #<QrScreenBase
        sta QrPpuLo
        lda #>QrScreenBase
        sta QrPpuHi
        lda #QrTileCount
        sta QrScreenRows
@row:
        ldx QrPpuHi
        lda QrPpuLo
        jsr QrSetPpuAddr
        ldy #0
@tile:
        lda (PtrA),y
        sta PpuData2007
        iny
        cpy #QrTileCount
        bne @tile

        lda PtrA                        ; next nametable row
        clc
        adc #QrTileCount
        sta PtrA
        lda PtrA + 1
        adc #0
        sta PtrA + 1

        lda QrPpuLo                     ; next screen row
        clc
        adc #32
        sta QrPpuLo
        lda QrPpuHi
        adc #0
        sta QrPpuHi

        dec QrScreenRows
        bne @row
        rts

; Write A tiles from (PtrB) at the current PPU address.
QrWriteTiles:
        sta QrWriteCount
        ldy #0
@byte:
        lda (PtrB),y
        sta PpuData2007
        iny
        cpy QrWriteCount
        bne @byte
        rts

QrDrawCaptions:
        ldx #>QrPlayerCaptionAddr
        lda #<QrPlayerCaptionAddr
        jsr QrSetPpuAddr
        lda #<QrPlayerText
        sta PtrB
        lda #>QrPlayerText
        sta PtrB + 1
        lda #QrPlayerTextLen
        jsr QrWriteTiles
        lda QrDisplaySlot               ; digit tiles are $00-$09
        clc
        adc #1
        sta PpuData2007

        ldx #>QrScanCaptionAddr
        lda #<QrScanCaptionAddr
        jsr QrSetPpuAddr
        lda #<QrScanText
        sta PtrB
        lda #>QrScanText
        sta PtrB + 1
        lda #QrScanTextLen
        jsr QrWriteTiles

        ldx #>QrHoldCaptionAddr
        lda #<QrHoldCaptionAddr
        jsr QrSetPpuAddr
        lda #<QrHoldText
        sta PtrB
        lda #>QrHoldText
        sta PtrB + 1
        lda #QrHoldTextLen
        jmp QrWriteTiles

; --------------------------------------------------------------------------
; Dismissal: Up + Select + A, held for three seconds, on either controller.
; Deliberately awkward, so a player who walks away from a finished round comes
; back to a code still on screen. Letting go resets the count.
; --------------------------------------------------------------------------

QrWaitForDismiss:
        lda #0
        sta QrHoldCount
@frame:
        jsr WaitForVblank
        lda ControllerCurrent
        and #QrDismissMask
        cmp #QrDismissMask
        beq @held
        lda ControllerCurrent + 1
        and #QrDismissMask
        cmp #QrDismissMask
        beq @held
        lda #0
        sta QrHoldCount
        beq @frame                      ; always: A is zero
@held:
        inc QrHoldCount
        lda QrHoldCount
        cmp #QrHoldFrames
        bne @frame
        rts
