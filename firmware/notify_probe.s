.syntax unified
.cpu cortex-m0
.thumb
.text
.org 0x1930
    bl .Lecho
.org 0x7314
.Lcapacity:
.org 0x8a14
.Lsubmit:
.org 0xbc88
.Lclear_idle:
.org 0x12e50
.Lecho:
    // Matched FF13 event: r5 handle, r6 handle+value length, old sp+36 value.
    push {r4,r5,r6,r7,lr}
    sub sp, #28
    bl .Lclear_idle
    cmp r6, #3
    bne .Lreturn
    ldr r0, [sp, #84]
    uxtb r0, r0
    lsls r0, r0, #16
    orrs r0, r5
    str r0, [sp, #8]
    ldr r0, .Ldescriptor
    str r0, [sp]
    add r0, sp, #8
    str r0, [sp, #4]
    mrs r4, primask
    cpsid i
    ldr r0, .Lsleep
    ldrb r0, [r0]
    cmp r0, #0
    bne .Lrestore
    bl .Lcapacity
    cmp r0, #6
    bls .Lrestore
    mov r0, sp
    bl .Lsubmit
.Lrestore:
    msr primask, r4
.Lreturn:
    add sp, #28
    pop {r4,r5,r6,r7,pc}
.balign 4
.Ldescriptor: .word 0x00030900
.Lsleep: .word 0x00020038
