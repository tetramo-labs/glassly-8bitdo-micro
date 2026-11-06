/* Micro product 0x9020 only. Protocol derived from the pinned macOS updater using
 * REA method metadata and isolated instruction emulation. See docs/findings.md.
 * No arbitrary addresses, retries, or images. Back up before erasing, verify
 * plaintext before committing version and resetting. Failure leaves BOOT mode.
 */
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/hid/IOHIDManager.h>
#include <CommonCrypto/CommonDigest.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define BASE 0x01018000u
#define SIZE 0x13000u
#define VERSION_ADDRESS 0x01017040u
#define META_BASE 0x01017000u
#define META_SIZE 0x1000u

static uint16_t u16(const uint8_t *p) { return p[0] | ((uint16_t)p[1]<<8); }
static uint32_t u32(const uint8_t *p) { return u16(p) | ((uint32_t)u16(p+2)<<16); }
static void p16(uint8_t *p, uint16_t x) { p[0]=(uint8_t)x; p[1]=(uint8_t)(x>>8); }
static void p32(uint8_t *p, uint32_t x) { p16(p,(uint16_t)x); p16(p+2,(uint16_t)(x>>16)); }
static uint16_t crc16(const uint8_t *p, size_t n) {
    uint16_t c=0xffff;
    for (size_t i=0;i<n;i++) { c^=p[i]; for(int b=0;b<8;b++) c=(c>>1)^((c&1)?0xa001:0); }
    return c;
}
static int packet(uint8_t out[64], uint16_t cmd, uint32_t addr, uint32_t total,
                  const uint8_t *data, uint16_t n) {
    if(n>46) return 0;
    memset(out,0,64); out[0]=5; p16(out+1,cmd); p16(out+5,n);
    p32(out+9,total); p32(out+13,addr);
    if(data) memcpy(out+17,data,n);
    p16(out+7,crc16(out+17,n));
    return 1;
}
static int ack(const uint8_t *r, size_t n, uint16_t cmd) {
    return n>=18 && n<=64 && r[0]==0 && r[1]==5 && u16(r+2)==0 && u16(r+4)==cmd;
}
static int read_reply(const uint8_t *r, size_t n, uint16_t cmd, uint32_t addr, uint16_t want) {
    if(!ack(r,n,cmd)) return 0;
    unsigned len=u16(r+6);
    if(len<want || len>46 || n<18+len || crc16(r+18,len)!=u16(r+8)) return 0;
    return cmd!=5 || (len==want && u32(r+10)==want && u32(r+14)==addr);
}
static void hash(const uint8_t *b,size_t n,char out[65]) {
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256(b,(CC_LONG)n,digest);
    for(unsigned i=0;i<sizeof(digest);i++) snprintf(out+2*i,3,"%02x",digest[i]);
}
static void dump(const char *label,const uint8_t *b,size_t n) {
    printf("%s=",label);for(size_t i=0;i<n;i++)printf("%02x",b[i]);putchar('\n');fflush(stdout);
}
static uint8_t reply[64]; static CFIndex reply_size; static int received;
static void input(void *ctx,IOReturn result,void *sender,IOHIDReportType type,
                  uint32_t id,uint8_t *r,CFIndex n) {
    (void)ctx;(void)sender;
    if(result || type!=kIOHIDReportTypeInput || id || n<0 || n>64) {received=-1;return;}
    memcpy(reply,r,(size_t)n); reply_size=n; received=1; dump("rx",r,(size_t)n);
}
static int exchange(IOHIDDeviceRef dev,uint16_t cmd,uint32_t address,uint32_t total,
                    const uint8_t *data,uint16_t n,int wait) {
    uint8_t out[64]; if(!packet(out,cmd,address,total,data,n))return 0;
    received=0;reply_size=0;dump("tx",out,64);
    IOReturn status=IOHIDDeviceSetReport(dev,kIOHIDReportTypeOutput,0,out,64);
    if(status) {fprintf(stderr,"SetReport command %u failed: %08x\n",cmd,(unsigned)status);return 0;}
    if(!wait)return 1;
    CFAbsoluteTime deadline=CFAbsoluteTimeGetCurrent()+(cmd==4?10.0:3.0);
    while(!received && CFAbsoluteTimeGetCurrent()<deadline)CFRunLoopRunInMode(kCFRunLoopDefaultMode,0.01,true);
    if(received!=1 || !ack(reply,(size_t)reply_size,cmd)) {
        fprintf(stderr,"No successful command-%u acknowledgement at %08x\n",cmd,address);return 0;
    }
    return 1;
}
static int read_range(IOHIDDeviceRef dev,uint32_t addr,uint8_t *out,unsigned count) {
    for(unsigned off=0;off<count;) {
        unsigned n=count-off<32?count-off:32;
        if(!exchange(dev,5,addr+off,n,NULL,(uint16_t)n,1) ||
           !read_reply(reply,(size_t)reply_size,5,addr+off,(uint16_t)n))return 0;
        memcpy(out+off,reply+18,n);off+=n;
    }
    return 1;
}
static int save(const char *dir,const char *name,const uint8_t *data,size_t n) {
    char path[4096];int used=snprintf(path,sizeof(path),"%s/%s",dir,name);
    if(used<0 || (size_t)used>=sizeof(path))return 0;
    FILE *f=fopen(path,"wbx");if(!f){perror(path);return 0;}
    int ok=fwrite(data,1,n,f)==n;
    if(fflush(f) || fsync(fileno(f)))ok=0;
    if(fclose(f))ok=0;
    return ok;
}
static uint8_t *load(const char *path,size_t n) {
    FILE *f=fopen(path,"rb");if(!f)return NULL;
    uint8_t *b=malloc(n);if(!b){fclose(f);return NULL;}
    int ok=fread(b,1,n,f)==n && fgetc(f)==EOF && !ferror(f);
    fclose(f);if(!ok){free(b);return NULL;}return b;
}
static void match(CFMutableDictionaryRef d,CFStringRef key,int32_t x) {
    CFNumberRef n=CFNumberCreate(NULL,kCFNumberSInt32Type,&x);CFDictionarySetValue(d,key,n);CFRelease(n);
}
static const uint8_t descriptor[]={5,140,9,1,161,1,9,3,21,0,38,0,255,117,8,149,64,129,2,9,4,21,0,38,0,255,117,8,149,64,145,2,192};
static const char *stock_hash="e31c7f7656fb041ec6ede6603762d841783eb3d9b760321eaaa0c582aaa59233";
static const char *notify_hash="1c172f49d5cf74e9443277f4b904ad61fe7021c0c957acc2da2e5b91ed50a456";
static const char *probe_hash="fca4e5698166c69b67feabcce95e6674d7afcd72478f9acb25c3b9b71caf6e8e";


/* Exact original image of the development unit; independently read twice.
 * Other factory tails remain rejected after backup, rather than guessed compatible. */
static const char *factory_hash="7e758f2da3fdd4675fd67a9853ef70aed3e8b9c8dec8895c77338699e2e70541";

int main(int argc,char **argv) {
    if(argc!=6 || strcmp(argv[1],"--apply")) {
        fprintf(stderr,"Usage: %s --apply USB_LOCATION full.dat expected-plaintext.bin NEW_BACKUP_DIR\n",argv[0]);return 2;
    }
    char *end;errno=0;unsigned long location=strtoul(argv[2],&end,0);
    if(errno || !*argv[2] || *end || !location || location>UINT32_MAX)return 2;
    uint8_t *dat=load(argv[3],77852),*expected=load(argv[4],SIZE);
    if(!dat || !expected){fprintf(stderr,"Cannot read exact-sized firmware inputs\n");return 2;}
    char dh[65],ph[65];hash(dat,77852,dh);hash(expected,SIZE,ph);
    int stock=!strcmp(dh,"74f0a12709758cc13a358e44adaa1d6193a3532aac2685db07e913c8e3609ce6") && !strcmp(ph,stock_hash);
    int probe=!strcmp(dh,"6c12c506242b60c75c446cfa9bff265102b214aa6d5e5afb7aa63f33c88c7d1a") && !strcmp(ph,probe_hash);
    int notify=!strcmp(dh,"e86ba128884dd1a741bcefd21d4978b2a7757a94d00c42d315b424097cd598c3") && !strcmp(ph,notify_hash);
    if(!stock && !probe && !notify){fprintf(stderr,"Refusing unreviewed image/payload hash pair\n");return 2;}
    const uint8_t *header=dat,*ciphertext=header+28;
    if(u32(header)!=105 || u32(header+4)!=BASE || u32(header+8)!=SIZE || u32(header+12)!=0x9020)return 2;
    printf("image_sha256=%s\nplaintext_sha256=%s\n",dh,ph);
    CFMutableDictionaryRef d=CFDictionaryCreateMutable(NULL,0,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
    match(d,CFSTR(kIOHIDVendorIDKey),0x2dc8);match(d,CFSTR(kIOHIDProductIDKey),0x3208);match(d,CFSTR(kIOHIDLocationIDKey),(int32_t)location);
    IOHIDManagerRef manager=IOHIDManagerCreate(NULL,kIOHIDOptionsTypeNone);
    IOHIDManagerSetDeviceMatching(manager,d);CFRelease(d);
    CFSetRef devices=IOHIDManagerCopyDevices(manager);
    if(!devices || CFSetGetCount(devices)!=1){fprintf(stderr,"Expected exactly one bootloader at specified USB location\n");return 3;}
    IOHIDDeviceRef dev;CFSetGetValues(devices,(const void **)&dev);
    CFTypeRef desc=IOHIDDeviceGetProperty(dev,CFSTR(kIOHIDReportDescriptorKey));
    CFTypeRef product=IOHIDDeviceGetProperty(dev,CFSTR(kIOHIDProductKey));
    CFTypeRef transport=IOHIDDeviceGetProperty(dev,CFSTR(kIOHIDTransportKey));
    if(!desc || CFGetTypeID(desc)!=CFDataGetTypeID() || CFDataGetLength(desc)!=sizeof(descriptor) ||
       memcmp(CFDataGetBytePtr(desc),descriptor,sizeof(descriptor)) || !product ||
       !CFEqual(product,CFSTR("8BitDo Boot")) || !transport || !CFEqual(transport,CFSTR("USB")))return 3;
    if(IOHIDDeviceOpen(dev,kIOHIDOptionsTypeNone)){fprintf(stderr,"Cannot open bootloader\n");return 3;}
    uint8_t incoming[64];int success=0;
    IOHIDDeviceRegisterInputReportCallback(dev,incoming,64,input,NULL);
    IOHIDDeviceScheduleWithRunLoop(dev,CFRunLoopGetCurrent(),kCFRunLoopDefaultMode);
    uint8_t *backup=malloc(SIZE),*verify=malloc(SIZE),metadata[META_SIZE];
    if(!backup || !verify)goto done;
    if(!exchange(dev,8,0,2,NULL,2,1) || !read_reply(reply,(size_t)reply_size,8,0,2) || u16(reply+18)!=0x9020)goto done;
    if(!read_range(dev,BASE,backup,SIZE) || !save(argv[5],"before-application.bin",backup,SIZE))goto done;
    if(!read_range(dev,META_BASE,metadata,META_SIZE) || !save(argv[5],"before-metadata.bin",metadata,META_SIZE))goto done;
    hash(backup,SIZE,ph);printf("backup_sha256=%s\n",ph);
    if(strcmp(ph,stock_hash) && strcmp(ph,probe_hash) && strcmp(ph,notify_hash) && strcmp(ph,factory_hash)){fprintf(stderr,"Unexpected installed baseline; backup saved, no erase performed\n");goto done;}
    if(u32(metadata+0x40)!=105){fprintf(stderr,"Unexpected version record; no erase performed\n");goto done;}
    if(!save(argv[5],"target.dat",dat,77852) || !save(argv[5],"expected.bin",expected,SIZE))goto done;
    fprintf(stderr,"Backup saved. Erasing application and vendor version record.\n");
    if(!exchange(dev,4,BASE,SIZE,NULL,0,1) || !exchange(dev,4,VERSION_ADDRESS,32,NULL,0,1))goto done;
    for(unsigned off=0;off<SIZE;) {
        unsigned n=SIZE-off<46?SIZE-off:46;
        if(!exchange(dev,3,BASE+off,SIZE,ciphertext+off,(uint16_t)n,1))goto done;
        off+=n;if(off%4094<46 || off==SIZE)fprintf(stderr,"Written %u/%u\n",off,SIZE);
    }
    if(!read_range(dev,BASE,verify,SIZE) || !save(argv[5],"after-application.bin",verify,SIZE))goto done;
    if(memcmp(verify,expected,SIZE)){fprintf(stderr,"PLAINTEXT VERIFICATION FAILED; no version commit/reset\n");goto done;}
    fprintf(stderr,"All %u plaintext bytes verified. Committing version 105.\n",SIZE);
    if(!exchange(dev,2,VERSION_ADDRESS,4,header,4,1))goto done;
    uint8_t version[4];
    if(!read_range(dev,VERSION_ADDRESS,version,4) || u32(version)!=105)goto done;
    if(!read_range(dev,META_BASE,metadata,META_SIZE) || !save(argv[5],"after-metadata.bin",metadata,META_SIZE))goto done;
    if(!exchange(dev,7,0,0,NULL,0,0))goto done;
    success=1;fprintf(stderr,"Verified firmware and version; reset sent. Check runtime USB identity.\n");
done:
    printf("flash_verified_and_reset_sent=%s\n",success?"true":"false");
    IOHIDDeviceUnscheduleFromRunLoop(dev,CFRunLoopGetCurrent(),kCFRunLoopDefaultMode);
    IOHIDDeviceClose(dev,kIOHIDOptionsTypeNone);CFRelease(devices);CFRelease(manager);
    free(backup);free(verify);free(dat);free(expected);
    return success?0:4;
}
