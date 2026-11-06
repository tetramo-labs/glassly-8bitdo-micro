/* Micro read-only identity/application/metadata backup. No arbitrary addresses,
 * writes, erase, reset, ROM or peripheral-register access. Packet constructor
 * independently checked against macOS updater boot type 17 in offline emulation.
 */
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/hid/IOHIDManager.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int received;
static unsigned expected_command;
static unsigned expected_bytes;
static uint32_t expected_address;
static FILE *image;
static uint8_t last_data[46];
static uint16_t crc16(const uint8_t *data, unsigned size) {
    uint16_t crc = 0xffff; /* vendor 0x10009b70, polynomial table at 0x101aee94 */
    for (unsigned i=0; i<size; ++i) {
        crc ^= data[i];
        for (unsigned bit=0; bit<8; ++bit) crc = (crc >> 1) ^ ((crc & 1) ? 0xa001 : 0);
    }
    return crc;
}
static uint32_t le32(const uint8_t *p) {
    return p[0] | ((uint32_t)p[1]<<8) | ((uint32_t)p[2]<<16) | ((uint32_t)p[3]<<24);
}
static void put32(uint8_t *p, uint32_t value) {
    for (unsigned i=0; i<4; ++i) p[i] = (uint8_t)(value >> (i*8));
}
static const uint8_t descriptor[] = {
    0x05,0x8c,0x09,0x01,0xa1,0x01,0x09,0x03,0x15,0x00,0x26,0x00,0xff,
    0x75,0x08,0x95,0x40,0x81,0x02,0x09,0x04,0x15,0x00,0x26,0x00,0xff,
    0x75,0x08,0x95,0x40,0x91,0x02,0xc0
};
static void dump(const char *label, const uint8_t *data, CFIndex length) {
    printf("%s=", label);
    for (CFIndex i=0; i<length; ++i) printf("%02x", data[i]);
    putchar('\n');
    fflush(stdout);
}

static void input(void *context, IOReturn result, void *sender,
                  IOHIDReportType type, uint32_t report_id,
                  uint8_t *report, CFIndex length) {
    (void)context; (void)sender;
    printf("input_result=0x%08x type=%d report_id=%u length=%ld\n",
           (unsigned)result, (int)type, report_id, (long)length);
    if (result != kIOReturnSuccess || length < 0 || length > 64) return;
    dump("response", report, length);
    /* ReadHid strips Windows' report-ID byte. The observed protocol reply
     * itself starts with 00 05; keep the vendor's data offset 18 unchanged. */
    if (type == kIOHIDReportTypeInput && report_id == 0 && length >= 18 &&
        report[0] == 0 && report[1] == 5 &&
        report[4] == expected_command && report[5] == 0) {
        unsigned status = report[2] | ((unsigned)report[3] << 8);
        printf("protocol_status=%u\n", status);
        received = status ? -1 : 1;
        unsigned payload_bytes = report[6] | ((unsigned)report[7]<<8);
        if (!status &&
            (payload_bytes < expected_bytes || payload_bytes > 46 ||
             length < (CFIndex)(18 + payload_bytes) ||
             crc16(report+18, payload_bytes) != (report[8] | ((unsigned)report[9]<<8)) ||
             (expected_command == 5 &&
              (payload_bytes != expected_bytes || le32(report+10) != expected_bytes ||
               le32(report+14) != expected_address)))) {
            fprintf(stderr, "Read response length/address/CRC mismatch\n");
            received = -1;
        }
        if (received == 1 && length >= (CFIndex)(18 + expected_bytes)) {
            memcpy(last_data,report+18,expected_bytes);
            dump("query_data", report+18, expected_bytes);
            if (image && fwrite(report+18, 1, expected_bytes, image) != expected_bytes) received = -1;
        } else if (!status) received = -1;
    }
}

static void match_number(CFMutableDictionaryRef dict, CFStringRef key, int32_t value) {
    CFNumberRef number = CFNumberCreate(kCFAllocatorDefault, kCFNumberSInt32Type, &value);
    CFDictionarySetValue(dict, key, number);
    CFRelease(number);
}


static int exchange(IOHIDDeviceRef dev, unsigned command, uint32_t address, unsigned count) {
    if (count > 32) return 0;
    expected_command=command; expected_address=address; expected_bytes=count;
    uint8_t packet[64]={5}; packet[1]=(uint8_t)command; packet[5]=(uint8_t)count;
    uint16_t crc=crc16(packet+17,count); packet[7]=(uint8_t)crc; packet[8]=(uint8_t)(crc>>8);
    put32(packet+9,count); put32(packet+13,address); received=0;
    IOReturn result=IOHIDDeviceSetReport(dev,kIOHIDReportTypeOutput,0,packet,64);
    CFAbsoluteTime deadline=CFAbsoluteTimeGetCurrent()+3;
    while (!result && !received && CFAbsoluteTimeGetCurrent()<deadline)
        CFRunLoopRunInMode(kCFRunLoopDefaultMode,0.05,true);
    return !result && received==1;
}
int main(int argc,char **argv) {
    if (argc<3 || argc>4) { fprintf(stderr,"Usage: %s USB_LOCATION identity|app-header|app-image|metadata [NEW_OUTPUT_FILE]\n",argv[0]); return 2; }
    char *end; errno=0; unsigned long location=strtoul(argv[1],&end,0);
    int identity=!strcmp(argv[2],"identity"), header=!strcmp(argv[2],"app-header");
    int app=!strcmp(argv[2],"app-image"), metadata=!strcmp(argv[2],"metadata");
    if (errno || !*argv[1] || *end || !location || location>UINT32_MAX ||
        !(identity||header||app||metadata) || argc!=(app||metadata ? 4 : 3)) return 2;
    CFMutableDictionaryRef match=CFDictionaryCreateMutable(NULL,0,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
    match_number(match,CFSTR(kIOHIDVendorIDKey),0x2dc8);
    match_number(match,CFSTR(kIOHIDProductIDKey),0x3208);
    match_number(match,CFSTR(kIOHIDLocationIDKey),(int32_t)location);
    IOHIDManagerRef manager=IOHIDManagerCreate(NULL,kIOHIDOptionsTypeNone);
    IOHIDManagerSetDeviceMatching(manager,match); CFRelease(match);
    CFSetRef devices=IOHIDManagerCopyDevices(manager);
    if (!devices || CFSetGetCount(devices)!=1) { fprintf(stderr,"Expected one bootloader at specified location\n"); return 3; }
    IOHIDDeviceRef dev; CFSetGetValues(devices,(const void **)&dev);
    CFTypeRef desc=IOHIDDeviceGetProperty(dev,CFSTR(kIOHIDReportDescriptorKey));
    CFTypeRef name=IOHIDDeviceGetProperty(dev,CFSTR(kIOHIDProductKey));
    CFTypeRef transport=IOHIDDeviceGetProperty(dev,CFSTR(kIOHIDTransportKey));
    if (!desc || CFGetTypeID(desc)!=CFDataGetTypeID() || CFDataGetLength(desc)!=sizeof descriptor ||
        memcmp(CFDataGetBytePtr(desc),descriptor,sizeof descriptor) || !name || !CFEqual(name,CFSTR("8BitDo Boot")) ||
        !transport || !CFEqual(transport,CFSTR("USB"))) return 4;
    if (IOHIDDeviceOpen(dev,kIOHIDOptionsTypeNone)) return 5;
    uint8_t incoming[64];
    IOHIDDeviceRegisterInputReportCallback(dev,incoming,64,input,NULL);
    IOHIDDeviceScheduleWithRunLoop(dev,CFRunLoopGetCurrent(),kCFRunLoopDefaultMode);
    int success=exchange(dev,8,0,2) && last_data[0]==0x20 && last_data[1]==0x90;
    if (!success) fprintf(stderr,"No verified Micro boot identity; refusing memory reads\n");
    unsigned completed=0, total=identity ? 0 : header ? 32 : metadata ? 4096 : 77824;
    uint32_t base=metadata ? 0x01017000 : 0x01018000;
    if (success && (app||metadata)) { image=fopen(argv[3],"wbx"); if (!image) { perror("Create new backup"); success=0; } }
    while (success && completed<total) {
        success=exchange(dev,5,base+completed,32);
        if (success) completed+=32;
    }
    if (image && fclose(image)) success=0;
    printf("completed=%u expected=%u success=%s\n",completed,total,success ? "true" : "false");
    IOHIDDeviceUnscheduleFromRunLoop(dev,CFRunLoopGetCurrent(),kCFRunLoopDefaultMode);
    IOHIDDeviceClose(dev,kIOHIDOptionsTypeNone); CFRelease(devices); CFRelease(manager);
    return success ? 0 : 6;
}
