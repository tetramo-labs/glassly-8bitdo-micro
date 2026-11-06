#define main flash_program_main
#include "../tools/flash_micro.c"
#undef main
#include <assert.h>

int main(void) {
    /* Native ARM64 constructor outputs from inspect_macos_updater.py. */
    const uint8_t erase_header[]={5,4,0,0,0,0,0,255,255,0,48,1,0,0,128,1,1};
    const uint8_t version_header[]={5,2,0,0,0,4,0,29,184,4,0,0,0,64,112,1,1};
    const uint8_t write_header[]={5,3,0,0,0,46,0,237,124,0,48,1,0,0,128,1,1};
    uint8_t p[64], version[4]={105,0,0,0};
    assert(packet(p,4,BASE,SIZE,NULL,0));
    assert(!memcmp(p,erase_header,sizeof(erase_header)));
    assert(packet(p,2,VERSION_ADDRESS,4,version,4));
    assert(!memcmp(p,version_header,sizeof(version_header)));
    uint8_t payload[46];for(unsigned i=0;i<46;i++)payload[i]=(uint8_t)i;
    assert(packet(p,3,BASE,SIZE,payload,46));
    assert(!memcmp(p,write_header,sizeof(write_header)) && !memcmp(p+17,payload,46) && p[63]==0);
    assert(!packet(p,3,BASE,SIZE,p,47));
    uint8_t response[64]={0,5};p16(response+4,5);p16(response+6,32);
    p32(response+10,32);p32(response+14,BASE);p16(response+8,crc16(response+18,32));
    assert(read_reply(response,64,5,BASE,32));
    assert(!read_reply(response,49,5,BASE,32));
    assert(!read_reply(response,65,5,BASE,32));
    assert(!read_reply(response,64,5,BASE+32,32));
    response[18]^=1;assert(!read_reply(response,64,5,BASE,32));response[18]^=1;
    response[2]=1;assert(!ack(response,64,5));response[2]=0;
    response[1]=4;assert(!ack(response,64,5));response[1]=5;
    response[4]=3;assert(!ack(response,64,5));assert(ack(response,64,3));
    puts("Flasher native packet goldens and malformed-response checks passed (no hardware)");
    return 0;
}
