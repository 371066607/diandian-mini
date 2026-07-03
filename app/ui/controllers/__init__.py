"""Domain controllers extracted from the QmlBridge god object.

QmlBridge (app/ui/qml_bridge.py) remains the aggregate root and the only
QObject QML binds to — its @Slot/@Property surface and Signal declarations
must stay exactly as-is, since QML connects to them directly. These
controllers are plain (non-QObject) classes that hold the *decision logic*
for one domain; QmlBridge's slots become thin shims that call into them and
then handle Qt-specific concerns (async dispatch via _run, signal emission)
themselves.

Only a first slice (api log, settings-save validation) has been extracted so
far — this is a large, ongoing decomposition (see AGENTS.md/CLAUDE.md), not a
single change. Extract further domains the same way: move the pure logic
here, leave signal emission and _run/self.services plumbing in the shim.
"""
