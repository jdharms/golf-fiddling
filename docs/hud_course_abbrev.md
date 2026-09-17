# HUD Course Abbreviation

> **Note**: This document was authored in full by jdharms, no AI assistance

In the top left of the in-game HUD, there is a block that displays the current course/hole status.
In the vanilla game, it would read something like:

```
US 1H
PAR 4

328 y
```

The only thing we really want to change here for the randomizer is the `US` abbreviation.

As a minor code size optimization, these letters for the three vanilla courses, JP, US, and UK,
are stored in program ROM: `JUUPSK`.

The actual bytes are: `13 1E 1E 19 1C 14` at PRG address $35C47.

The routine that reads them:

```
                   --------LD_9BE1--------
                   LD_9BE1:
35BE1  20 1A D4       JSR LD41A
35BE4               --------data--------
35BE4  00 00 00 00 00 00 .db $2F $9C $10 $04 $18 $00
35BE9               ----------------
35BEA  AE 02 01       LDX CurrCourse
35BED  BD 47 9C       LDA $9C47,X
35BF0  8D 14 04       STA $0414
35BF3  BD 4A 9C       LDA $9C4A,X
35BF6  8D 15 04       STA $0415
35BF9  A0 03          LDY #$03
35BFB  A5 94          LDA HoleNumber
35BFD  18             CLC
35BFE  69 01          ADC #$01
35C00  C9 0A          CMP #$0A
35C02  90 07          BCC LD_9C0B
35C04  E9 0A          SBC #$0A
35C06  A0 01          LDY #$01
35C08  8C 16 04       STY $0416
                   LD_9C0B:
35C0B  8D 17 04       STA $0417
35C0E  AD 09 01       LDA Par
35C11  8D 1D 04       STA $041D
35C14  AD 0A 01       LDA DistanceHundredsBCD
35C17  8D 23 04       STA $0423
35C1A  AD 0B 01       LDA DistanceTensBCD
35C1D  8D 24 04       STA $0424
35C20  AD 0C 01       LDA DistanceOnesBCD
35C23  8D 25 04       STA $0425
```

In my opinion, the easiest change to make these always read "RN" for "random" would be to change
the six bytes to: `1B 1B 1B 17 17 17`

In theory only the ones for the course(s) we care about need to be changed, but it's cheap/
free to just change all three courses.