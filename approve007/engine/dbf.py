# -*- coding: utf-8 -*-
"""
DBF reader แบบ read-only (zero-dependency) — โครงเดียวกับ so_push.py / checkso.py ที่ใช้งานจริงแล้ว
เปิดไฟล์ด้วยโหมด "rb" เท่านั้น ไม่ล็อก ไม่เขียน DBF ของ Express (HANDOVER ข้อ 9.5)
"""
import datetime
import struct


def fields_of(path):
    """คืนรายชื่อฟิลด์ [(name, type, len)] — ใช้ตอน PRE-FLIGHT ตรวจว่า Express มีคอลัมน์ที่ต้องใช้"""
    with open(path, "rb") as f:
        hdr = f.read(32)
        hdrlen = struct.unpack("<H", hdr[8:10])[0]
        out = []
        for _ in range((hdrlen - 33) // 32):
            fd = f.read(32)
            if fd[0:1] == b"\r":
                break
            out.append((fd[0:11].split(b"\x00")[0].decode("ascii", "replace"),
                        fd[11:12].decode("ascii", "replace"), fd[16]))
        return out


def read_dbf(path, keep=None, encoding="cp874"):
    """yield dict ต่อแถว · keep = set ของฟิลด์ที่ต้องการ (None = ทุกฟิลด์) · ข้ามแถวที่ถูกลบ (*)"""
    with open(path, "rb") as f:
        hdr = f.read(32)
        nrec = struct.unpack("<I", hdr[4:8])[0]
        hdrlen = struct.unpack("<H", hdr[8:10])[0]
        reclen = struct.unpack("<H", hdr[10:12])[0]
        fdefs = []
        for _ in range((hdrlen - 33) // 32):
            fd = f.read(32)
            if fd[0:1] == b"\r":
                break
            fdefs.append((fd[0:11].split(b"\x00")[0].decode("ascii", "replace"),
                          fd[11:12].decode("ascii", "replace"), fd[16]))
        f.seek(hdrlen)
        for _ in range(nrec):
            rec = f.read(reclen)
            if len(rec) < reclen:
                break
            if rec[0:1] == b"*":
                continue
            row, pos = {}, 1
            for name, ftype, flen in fdefs:
                raw = rec[pos:pos + flen]
                pos += flen
                if keep is not None and name not in keep:
                    continue
                row[name] = _decode(raw, ftype, flen, encoding)
            yield row


def _decode(raw, ftype, flen, encoding):
    if ftype in ("N", "F"):
        s = raw.strip()
        try:
            return float(s) if s else 0.0
        except ValueError:
            return 0.0
    if ftype == "B" and flen == 8:
        return struct.unpack("<d", raw)[0]
    if ftype == "I" and flen == 4:
        return float(struct.unpack("<i", raw)[0])
    if ftype == "Y" and flen == 8:
        return struct.unpack("<q", raw)[0] / 10000.0
    if ftype == "D":
        s = raw.strip()
        if len(s) == 8 and s.isdigit():
            try:
                return datetime.date(int(s[:4]), int(s[4:6]), int(s[6:8]))
            except ValueError:
                return None
        return None
    if ftype == "L":
        return raw in (b"T", b"t", b"Y", b"y")
    return raw.decode(encoding, "replace").strip()
