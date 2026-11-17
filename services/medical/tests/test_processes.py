"""Process restart decisions with fake identities/signals; never stop a real process."""

import os
import signal

import pytest

from medical_service import processes
from medical_service.processes import ProcessIdentity
from medical_service.validation import ServiceError


@pytest.fixture
def busy(monkeypatch):
    old = ProcessIdentity(1234, "start-1", os.geteuid(), True)
    monkeypatch.setattr(processes, "port_is_free", lambda: False)
    monkeypatch.setattr(processes, "model_port_listeners", lambda: [old])
    monkeypatch.setattr(processes, "process_identity", lambda _: old)
    calls = []
    monkeypatch.setattr(processes.os, "kill", lambda *args: calls.append(args))
    return old, calls


def test_free_port_does_not_signal_anyone(monkeypatch):
    monkeypatch.setattr(processes, "port_is_free", lambda: True)
    monkeypatch.setattr(
        processes.os, "kill", lambda *args: pytest.fail("No process may be stopped")
    )
    processes.ensure_port_available()


def test_stops_only_the_identified_service_then_waits_for_free_port(busy, monkeypatch):
    old, calls = busy
    ports = iter([False, True])
    identities = iter([old, old, None])
    monkeypatch.setattr(processes, "port_is_free", lambda: next(ports))
    monkeypatch.setattr(processes, "process_identity", lambda _: next(identities))
    monkeypatch.setattr(processes.time, "sleep", lambda _: None)
    processes.ensure_port_available()
    assert calls == [(1234, signal.SIGTERM)]


@pytest.mark.parametrize(
    "pid,owned,recognised,code",
    [
        (1, True, True, "MODEL_SERVICE_REFUSE_PID1_OR_SELF"),
        (1234, True, False, "MODEL_SERVICE_REFUSE_UNRELATED_PROCESS"),
        (1234, False, True, "MODEL_SERVICE_REFUSE_UNRELATED_PROCESS"),
    ],
)
def test_never_signals_pid1_unrelated_or_unowned_service(
    busy, monkeypatch, pid, owned, recognised, code
):
    _, calls = busy
    identity = ProcessIdentity(pid, "s", os.geteuid() if owned else os.geteuid() + 1, recognised)
    monkeypatch.setattr(processes, "model_port_listeners", lambda: [identity])
    with pytest.raises(ServiceError, match=code):
        processes.ensure_port_available()
    assert calls == []


@pytest.mark.parametrize("count", [0, 2])
def test_ambiguous_listeners_are_not_stopped(busy, monkeypatch, count):
    old, calls = busy
    monkeypatch.setattr(processes, "model_port_listeners", lambda: [old] * count)
    with pytest.raises(ServiceError, match="MODEL_SERVICE_LISTENER_AMBIGUOUS"):
        processes.ensure_port_available()
    assert calls == []


def test_reused_pid_is_not_signalled(busy, monkeypatch):
    old, calls = busy
    monkeypatch.setattr(
        processes,
        "process_identity",
        lambda _: ProcessIdentity(old.pid, "new-start", old.uid, True),
    )
    with pytest.raises(ServiceError, match="MODEL_SERVICE_PROCESS_CHANGED"):
        processes.ensure_port_available()
    assert calls == []


def test_stop_timeout_does_not_force_kill_or_start_second_service(busy, monkeypatch):
    _, calls = busy
    monkeypatch.setenv("MODEL_SERVICE_STOP_TIMEOUT_SECONDS", "1")
    clock = iter([0, 2])
    monkeypatch.setattr(processes.time, "monotonic", lambda: next(clock))
    with pytest.raises(ServiceError, match="MODEL_SERVICE_STOP_TIMEOUT"):
        processes.ensure_port_available()
    assert calls == [(1234, signal.SIGTERM)]


def test_proc_inspection_finds_only_listening_socket_8000(tmp_path, monkeypatch):
    net = tmp_path / "net"
    net.mkdir()
    (net / "tcp").write_text("header\n0: 00000000:1F40 00000000:0000 0A 0 0 0 0 0 42\n")
    proc = tmp_path / "1234"
    (proc / "fd").mkdir(parents=True)
    (proc / "fd/3").symlink_to("socket:[42]")
    (proc / "cmdline").write_bytes(b"python\0-m\0uvicorn\0medical_service.main:app\0")
    (proc / "stat").write_text(
        "1234 (python worker) " + " ".join(["S"] + ["0"] * 18 + ["start-42"])
    )
    monkeypatch.setattr(processes, "PROC_ROOT", tmp_path)
    listeners = processes.model_port_listeners()
    assert listeners == [ProcessIdentity(1234, "start-42", os.geteuid(), True)]
