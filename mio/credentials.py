"""Minimal Windows Credential Manager access. No plaintext fallback."""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import os


class _Credential(ctypes.Structure):
    _fields_ = [('Flags', wintypes.DWORD), ('Type', wintypes.DWORD), ('TargetName', wintypes.LPWSTR),
        ('Comment', wintypes.LPWSTR), ('LastWritten', wintypes.FILETIME), ('CredentialBlobSize', wintypes.DWORD),
        ('CredentialBlob', ctypes.POINTER(ctypes.c_ubyte)), ('Persist', wintypes.DWORD),
        ('AttributeCount', wintypes.DWORD), ('Attributes', ctypes.c_void_p),
        ('TargetAlias', wintypes.LPWSTR), ('UserName', wintypes.LPWSTR)]


class CredentialStore:
    def __init__(self, target='MioMusic/Spotify/SP_DC'):
        self.target = target

    def _api(self):
        if os.name != 'nt':
            raise ValueError('此平台不支持 Windows 凭据管理器，请取消保存，仅在本次会话使用。')
        api = ctypes.WinDLL('advapi32', use_last_error=True)
        api.CredWriteW.argtypes = [ctypes.POINTER(_Credential), wintypes.DWORD]
        api.CredWriteW.restype = wintypes.BOOL
        api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.POINTER(ctypes.POINTER(_Credential))]
        api.CredReadW.restype = wintypes.BOOL
        api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        api.CredDeleteW.restype = wintypes.BOOL
        api.CredFree.argtypes = [ctypes.c_void_p]
        return api

    def _error(self):
        raise ValueError(f'Windows 凭据管理器不可用（错误 {ctypes.get_last_error()}）。可以取消保存，仅在本次会话使用。')

    def read(self):
        api = self._api()
        pointer = ctypes.POINTER(_Credential)()
        if not api.CredReadW(self.target, 1, 0, ctypes.byref(pointer)):
            if ctypes.get_last_error() == 1168:
                return None
            self._error()
        try:
            c = pointer.contents
            return ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize).decode('utf-16-le')
        finally:
            api.CredFree(pointer)

    def write(self, value):
        raw = value.encode('utf-16-le')
        if len(raw) > 2560:
            raise ValueError('会话内容过长，请只粘贴 SP_DC 的值')
        blob = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
        credential = _Credential()
        credential.Type, credential.TargetName, credential.UserName = 1, self.target, 'Spotify session'
        credential.CredentialBlobSize, credential.CredentialBlob = len(raw), blob
        credential.Persist = 2
        if not self._api().CredWriteW(ctypes.byref(credential), 0):
            self._error()

    def delete(self):
        if not self._api().CredDeleteW(self.target, 1, 0) and ctypes.get_last_error() != 1168:
            self._error()
