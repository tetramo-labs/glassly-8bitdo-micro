/* Enter Micro update mode using the vendor's two runtime reports.
 * No erase/write-flash operation. Exact VID/PID/location/descriptor admission.
 */
#include <IOKit/hid/IOHIDManager.h>
#include <CommonCrypto/CommonDigest.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

static void match(CFMutableDictionaryRef d, CFStringRef key, int32_t value) {
    CFNumberRef n = CFNumberCreate(NULL, kCFNumberSInt32Type, &value);
    CFDictionarySetValue(d, key, n); CFRelease(n);
}
int main(int argc, char **argv) {
    if (argc != 3 || strcmp(argv[1], "--apply")) {
        fprintf(stderr,"Usage: %s --apply OBSERVED_USB_LOCATION\n",argv[0]); return 2;
    }
    char *end; errno=0; unsigned long loc=strtoul(argv[2],&end,0);
    if (errno || !*argv[2] || *end || !loc || loc>UINT32_MAX) return 2;
    IOHIDManagerRef manager=IOHIDManagerCreate(NULL,kIOHIDOptionsTypeNone);
    CFMutableDictionaryRef d=CFDictionaryCreateMutable(NULL,0,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
    match(d,CFSTR(kIOHIDVendorIDKey),0x2dc8);
    match(d,CFSTR(kIOHIDProductIDKey),0x9020);
    match(d,CFSTR(kIOHIDLocationIDKey),(int32_t)loc);
    IOHIDManagerSetDeviceMatching(manager,d); CFRelease(d);
    CFSetRef devices=IOHIDManagerCopyDevices(manager);
    if (!devices || CFSetGetCount(devices)!=1) { fprintf(stderr,"Expected one Micro runtime device at location\n"); return 3; }
    IOHIDDeviceRef dev; CFSetGetValues(devices,(const void **)&dev);
    CFTypeRef prop=IOHIDDeviceGetProperty(dev,CFSTR(kIOHIDReportDescriptorKey));
    if (!prop || CFGetTypeID(prop)!=CFDataGetTypeID() || CFDataGetLength(prop)!=136) return 4;
    unsigned char digest[32]; char hex[65];
    CC_SHA256(CFDataGetBytePtr(prop),(CC_LONG)CFDataGetLength(prop),digest);
    for (int i=0;i<32;i++) snprintf(hex+2*i,3,"%02x",digest[i]);
    if (strcmp(hex,"2c5b161fb5dafa36f3337fcc8ced3b6f806d14cf4563817b6a1696b86988c264")) return 4;
    IOReturn rc=IOHIDDeviceOpen(dev,kIOHIDOptionsTypeNone);
    if (rc) { fprintf(stderr,"Open failed: 0x%x\n",rc); return 5; }
    uint8_t first[64]={0x06,0x00,0x50,0x01,0x00,0x00};
    uint8_t legacy[64]={0x81,0x05,0x00,0x51,0x00,0x00};
    rc=IOHIDDeviceSetReport(dev,kIOHIDReportTypeOutput,0,first,sizeof first);
    printf("Vendor update-mode request result: 0x%x\n",rc);
    IOReturn second=IOHIDDeviceSetReport(dev,kIOHIDReportTypeOutput,0,legacy,sizeof legacy);
    printf("Vendor legacy fallback result: 0x%x\n",second);
    puts("Inspect USB enumeration to establish outcome; report delivery is not boot confirmation.");
    IOHIDDeviceClose(dev,kIOHIDOptionsTypeNone); CFRelease(devices); CFRelease(manager);
    return rc && second ? 6 : 0;
}
