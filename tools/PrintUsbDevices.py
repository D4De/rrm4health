import pyudev

context = pyudev.Context()

for device in context.list_devices(subsystem='usb'):
    print('Device path:', device.sys_path)
    print('Vendor:', device.get('ID_VENDOR_ID'))
    print('Product:', device.get('ID_MODEL_ID'))
    print('Product name:', device.get('ID_MODEL'))
    print('Bus:', device.get('ID_BUS'))
    print('---')

'''
Device path: /sys/devices/pci0000:00/0000:00:08.1/0000:04:00.3/usb1
Vendor: 1d6b
Product: 0002
Product name: xHCI_Host_Controller
Bus: usb
---
Device path: /sys/devices/pci0000:00/0000:00:08.1/0000:04:00.3/usb1/1-0:1.0
Vendor: None
Product: None
Product name: None
Bus: None
---
Device path: /sys/devices/pci0000:00/0000:00:08.1/0000:04:00.3/usb1/1-2
Vendor: 05e3
Product: 0610
Product name: USB2.1_Hub
Bus: usb
---
Device path: /sys/devices/pci0000:00/0000:00:08.1/0000:04:00.3/usb1/1-2/1-2.4
Vendor: 0bda
Product: a729
Product name: Bluetooth_5.3_Radio
Bus: usb
---
Device path: /sys/devices/pci0000:00/0000:00:08.1/0000:04:00.3/usb1/1-2/1-2.4/1-2.4:1.0
Vendor: None
Product: None
Product name: None
Bus: None
---
Device path: /sys/devices/pci0000:00/0000:00:08.1/0000:04:00.3/usb1/1-2/1-2.4/1-2.4:1.1
Vendor: None
Product: None
Product name: None
Bus: None
---
Device path: /sys/devices/pci0000:00/0000:00:08.1/0000:04:00.3/usb1/1-2/1-2:1.0
Vendor: None
Product: None
Product name: None
Bus: None
---
Device path: /sys/devices/pci0000:00/0000:00:08.1/0000:04:00.3/usb1/1-3
Vendor: 04f2
Product: b725
Product name: Integrated_Camera
Bus: usb
---
Device path: /sys/devices/pci0000:00/0000:00:08.1/0000:04:00.3/usb1/1-3/1-3:1.0
Vendor: None
Product: None
Product name: None
Bus: None
---
Device path: /sys/devices/pci0000:00/0000:00:08.1/0000:04:00.3/usb1/1-3/1-3:1.1
Vendor: None
Product: None
Product name: None
Bus: None
---
Device path: /sys/devices/pci0000:00/0000:00:08.1/0000:04:00.3/usb1/1-3/1-3:1.2
Vendor: None
Product: None
Product name: None
Bus: None
---
Device path: /sys/devices/pci0000:00/0000:00:08.1/0000:04:00.3/usb2
Vendor: 1d6b
Product: 0003
Product name: xHCI_Host_Controller
Bus: usb
---
Device path: /sys/devices/pci0000:00/0000:00:08.1/0000:04:00.3/usb2/2-0:1.0
Vendor: None
Product: None
Product name: None
Bus: None
---
Device path: /sys/devices/pci0000:00/0000:00:08.1/0000:04:00.3/usb2/2-2
Vendor: 05e3
Product: 0626
Product name: USB3.1_Hub
Bus: usb
---
Device path: /sys/devices/pci0000:00/0000:00:08.1/0000:04:00.3/usb2/2-2/2-2.1
Vendor: 152d
Product: 1580
Product name: HIKSEMI
Bus: usb
---
Device path: /sys/devices/pci0000:00/0000:00:08.1/0000:04:00.3/usb2/2-2/2-2.1/2-2.1:1.0
Vendor: None
Product: None
Product name: None
Bus: None
---
Device path: /sys/devices/pci0000:00/0000:00:08.1/0000:04:00.3/usb2/2-2/2-2:1.0
Vendor: None
Product: None
Product name: None
Bus: None
---
Device path: /sys/devices/pci0000:00/0000:00:08.1/0000:04:00.4/usb3
Vendor: 1d6b
Product: 0002
Product name: xHCI_Host_Controller
Bus: usb
---
Device path: /sys/devices/pci0000:00/0000:00:08.1/0000:04:00.4/usb3/3-0:1.0
Vendor: None
Product: None
Product name: None
Bus: None
---
Device path: /sys/devices/pci0000:00/0000:00:08.1/0000:04:00.4/usb3/3-1
Vendor: 03f0
Product: 0941
Product name: HP_X500_USB_Optical_Mouse
Bus: usb
---
Device path: /sys/devices/pci0000:00/0000:00:08.1/0000:04:00.4/usb3/3-1/3-1:1.0
Vendor: None
Product: None
Product name: None
Bus: None
---
Device path: /sys/devices/pci0000:00/0000:00:08.1/0000:04:00.4/usb3/3-4
Vendor: 0bda
Product: c123
Product name: Bluetooth_Radio
Bus: usb
---
Device path: /sys/devices/pci0000:00/0000:00:08.1/0000:04:00.4/usb3/3-4/3-4:1.0
Vendor: None
Product: None
Product name: None
Bus: None
---
Device path: /sys/devices/pci0000:00/0000:00:08.1/0000:04:00.4/usb3/3-4/3-4:1.1
Vendor: None
Product: None
Product name: None
Bus: None
---
Device path: /sys/devices/pci0000:00/0000:00:08.1/0000:04:00.4/usb4
Vendor: 1d6b
Product: 0003
Product name: xHCI_Host_Controller
Bus: usb
---
Device path: /sys/devices/pci0000:00/0000:00:08.1/0000:04:00.4/usb4/4-0:1.0
Vendor: None
Product: None
Product name: None
Bus: None

'''