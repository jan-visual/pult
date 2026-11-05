// Pult: nativní okno pro macOS. Zobrazuje lokální server Pultu ve WebKitu,
// má vlastní ikonu v Docku, mikrofon pro diktování, nahrávání souborů a stahování.
// Sestavuje ho install.py (swiftc z Command Line Tools), adresa a cesty jsou v Info.plist.
import Cocoa
import WebKit

let info = Bundle.main.infoDictionary ?? [:]
let pultURL = URL(string: (info["PultURL"] as? String) ?? "http://localhost:7858/")!
let appVersion = (info["CFBundleShortVersionString"] as? String) ?? "2"

func openExternal(_ u: URL) {
    // ven jen web a e-mail, nikdy file://, smb:// ani jiné aplikace
    if ["http", "https", "mailto"].contains(u.scheme?.lowercased() ?? "") { NSWorkspace.shared.open(u) }
}

func isLocal(_ url: URL?) -> Bool {
    guard let u = url else { return false }
    if u.scheme == "about" || u.scheme == "blob" || u.scheme == "data" { return true }
    guard u.scheme == "http" || u.scheme == "https" else { return false }
    return u.host == pultURL.host && (u.port ?? 80) == (pultURL.port ?? 80)
}

final class Pult: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var retries = 0
    var downloads: [ObjectIdentifier: URL] = [:]

    func applicationDidFinishLaunching(_ n: Notification) {
        buildMenu()
        let cfg = WKWebViewConfiguration()
        cfg.applicationNameForUserAgent = "Version/18.0 Safari/605.1.15 PultApp/\(appVersion)"
        cfg.mediaTypesRequiringUserActionForPlayback = []
        cfg.preferences.setValue(true, forKey: "developerExtrasEnabled")
        if #available(macOS 12.3, *) { cfg.preferences.isElementFullscreenEnabled = true }
        web = WKWebView(frame: .zero, configuration: cfg)
        web.navigationDelegate = self
        web.uiDelegate = self
        web.allowsBackForwardNavigationGestures = false
        web.allowsMagnification = true
        web.setValue(false, forKey: "drawsBackground")

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1440, height: 900),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "Pult"
        window.appearance = NSAppearance(named: .darkAqua)
        window.backgroundColor = NSColor(red: 0.043, green: 0.043, blue: 0.043, alpha: 1)
        window.minSize = NSSize(width: 760, height: 520)
        window.tabbingMode = .disallowed
        window.contentView = web
        window.delegate = self
        window.center()
        window.setFrameAutosaveName("PultMain")
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        load()
    }

    func load() { web.load(URLRequest(url: pultURL)) }

    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool { true }
    func applicationShouldHandleReopen(_ s: NSApplication, hasVisibleWindows f: Bool) -> Bool {
        window?.makeKeyAndOrderFront(nil); return true
    }

    // Server neběží: zkusíme ho nastartovat a načíst znovu.
    func webView(_ w: WKWebView, didFailProvisionalNavigation nav: WKNavigation!, withError e: Error) {
        let err = e as NSError
        if err.code == NSURLErrorCancelled || err.code == 102 { return }  // zrušeno / převedeno na stažení
        if !isLocal(w.url ?? pultURL) && w.url != nil { return }
        retries += 1
        if retries == 1 || retries % 10 == 0 { startServer() }
        let msg = retries < 3 ? "Starting Pult…" : "Waiting for the Pult server…"
        w.loadHTMLString("<html><body style='background:#0b0b0b;color:#9a9a98;font:15px -apple-system;display:grid;place-items:center;height:96vh'>\(msg)</body></html>", baseURL: nil)
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { self.load() }
    }
    func webView(_ w: WKWebView, didFinish nav: WKNavigation!) {
        guard isLocal(w.url), w.url?.scheme != "about" else { return }
        retries = 0
        importStorage()
    }

    // Jednorázový přenos nastavení z prohlížeče: migrate-storage.json vedle config.json ({"pult.name": "\"Jan\"", …}).
    func importStorage() {
        guard let c = info["PultConfig"] as? String else { return }
        let f = URL(fileURLWithPath: c).deletingLastPathComponent().appendingPathComponent("migrate-storage.json")
        guard let data = try? Data(contentsOf: f),
              let items = (try? JSONSerialization.jsonObject(with: data)) as? [String: String],
              let json = String(data: (try? JSONSerialization.data(withJSONObject: items)) ?? Data(), encoding: .utf8) else { return }
        web.evaluateJavaScript("(function(o){for(const k in o){if(k.indexOf('pult.')===0)localStorage.setItem(k,o[k])}return true})(\(json))") { r, err in
            if err == nil { try? FileManager.default.removeItem(at: f); self.load() }
        }
    }
    func webViewWebContentProcessDidTerminate(_ w: WKWebView) { load() }

    func startServer() {
        guard let py = info["PultPython"] as? String, let cli = info["PultCLI"] as? String else { return }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: py)
        p.arguments = [cli, "start"]
        var env = ProcessInfo.processInfo.environment
        if let c = info["PultConfig"] as? String { env["PULT_CONFIG"] = c }
        p.environment = env
        p.standardOutput = FileHandle.nullDevice; p.standardError = FileHandle.nullDevice
        try? p.run()
    }

    // Odkazy mimo Pult (web, mailto, ElevenLabs) jdou do výchozího prohlížeče / aplikace.
    func webView(_ w: WKWebView, decidePolicyFor a: WKNavigationAction, decisionHandler h: @escaping (WKNavigationActionPolicy) -> Void) {
        if #available(macOS 11.3, *), a.shouldPerformDownload { h(.download); return }
        if let u = a.request.url, !isLocal(u) {
            if a.targetFrame?.isMainFrame ?? true { openExternal(u); h(.cancel); return }
            h(.cancel); return  // cizí obsah ve vnořených rámech nepouštět
        }
        h(.allow)
    }
    func webView(_ w: WKWebView, decidePolicyFor r: WKNavigationResponse, decisionHandler h: @escaping (WKNavigationResponsePolicy) -> Void) {
        let disp = (r.response as? HTTPURLResponse)?.value(forHTTPHeaderField: "Content-Disposition") ?? ""
        if #available(macOS 11.3, *), (!r.canShowMIMEType || disp.lowercased().hasPrefix("attachment")) { h(.download); return }
        h(.allow)
    }
    // target=_blank a window.open
    func webView(_ w: WKWebView, createWebViewWith c: WKWebViewConfiguration, for a: WKNavigationAction, windowFeatures f: WKWindowFeatures) -> WKWebView? {
        if let u = a.request.url {
            openExternal(u)  // target=_blank: do výchozího prohlížeče, ať okno Pultu zůstane, kde je
        }
        return nil
    }

    // Mikrofon pro diktování (oprávnění systému řeší Info.plist).
    @available(macOS 12.0, *)
    func webView(_ w: WKWebView, requestMediaCapturePermissionFor o: WKSecurityOrigin, initiatedByFrame f: WKFrameInfo, type: WKMediaCaptureType, decisionHandler h: @escaping (WKPermissionDecision) -> Void) {
        let same = o.host == pultURL.host && o.port == (pultURL.port ?? 80) && o.protocol == (pultURL.scheme ?? "http")
        h(same && f.isMainFrame && type == .microphone ? .grant : .deny)  // jen mikrofon a jen pro Pult
    }

    // <input type=file>
    func webView(_ w: WKWebView, runOpenPanelWith p: WKOpenPanelParameters, initiatedByFrame f: WKFrameInfo, completionHandler h: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = p.allowsMultipleSelection
        panel.canChooseDirectories = p.allowsDirectories
        panel.canChooseFiles = true
        panel.beginSheetModal(for: window) { r in h(r == .OK ? panel.urls : nil) }
    }

    // alert / confirm / prompt
    func webView(_ w: WKWebView, runJavaScriptAlertPanelWithMessage m: String, initiatedByFrame f: WKFrameInfo, completionHandler h: @escaping () -> Void) {
        let a = NSAlert(); a.messageText = m; a.addButton(withTitle: "OK")
        a.beginSheetModal(for: window) { _ in h() }
    }
    func webView(_ w: WKWebView, runJavaScriptConfirmPanelWithMessage m: String, initiatedByFrame f: WKFrameInfo, completionHandler h: @escaping (Bool) -> Void) {
        let a = NSAlert(); a.messageText = m; a.addButton(withTitle: "OK"); a.addButton(withTitle: "Cancel")
        a.beginSheetModal(for: window) { r in h(r == .alertFirstButtonReturn) }
    }
    func webView(_ w: WKWebView, runJavaScriptTextInputPanelWithPrompt m: String, defaultText d: String?, initiatedByFrame f: WKFrameInfo, completionHandler h: @escaping (String?) -> Void) {
        let a = NSAlert(); a.messageText = m; a.addButton(withTitle: "OK"); a.addButton(withTitle: "Cancel")
        let t = NSTextField(frame: NSRect(x: 0, y: 0, width: 280, height: 24)); t.stringValue = d ?? ""
        a.accessoryView = t
        a.beginSheetModal(for: window) { r in h(r == .alertFirstButtonReturn ? t.stringValue : nil) }
    }

    // Stahování do složky Stažené soubory
    @available(macOS 11.3, *)
    func webView(_ w: WKWebView, navigationAction a: WKNavigationAction, didBecome d: WKDownload) { d.delegate = self }
    @available(macOS 11.3, *)
    func webView(_ w: WKWebView, navigationResponse r: WKNavigationResponse, didBecome d: WKDownload) { d.delegate = self }
    @available(macOS 11.3, *)
    func download(_ d: WKDownload, decideDestinationUsing r: URLResponse, suggestedFilename name: String, completionHandler h: @escaping (URL?) -> Void) {
        let dir = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask)[0]
        let base = (name as NSString).deletingPathExtension, ext = (name as NSString).pathExtension
        var url = dir.appendingPathComponent(name), i = 2
        while FileManager.default.fileExists(atPath: url.path) {
            url = dir.appendingPathComponent(ext.isEmpty ? "\(base) \(i)" : "\(base) \(i).\(ext)"); i += 1
        }
        downloads[ObjectIdentifier(d)] = url
        h(url)
    }
    @available(macOS 11.3, *)
    func downloadDidFinish(_ d: WKDownload) {
        if let u = downloads.removeValue(forKey: ObjectIdentifier(d)) { NSWorkspace.shared.activateFileViewerSelecting([u]) }
    }
    @available(macOS 11.3, *)
    func download(_ d: WKDownload, didFailWithError e: Error, resumeData: Data?) { downloads.removeValue(forKey: ObjectIdentifier(d)) }

    // Menu: bez Edit menu by nefungovalo ⌘C / ⌘V v textových polích.
    @objc func reload(_ s: Any?) { load() }
    @objc func zoomIn(_ s: Any?) { web.pageZoom = min(2, web.pageZoom + 0.1) }
    @objc func zoomOut(_ s: Any?) { web.pageZoom = max(0.5, web.pageZoom - 0.1) }
    @objc func zoomReset(_ s: Any?) { web.pageZoom = 1 }
    @objc func openInBrowser(_ s: Any?) { NSWorkspace.shared.open(web.url ?? pultURL) }

    func buildMenu() {
        let main = NSMenu()
        func sub(_ title: String, _ items: [NSMenuItem]) {
            let it = NSMenuItem(); let m = NSMenu(title: title)
            items.forEach { m.addItem($0) }; it.submenu = m; main.addItem(it)
        }
        func item(_ t: String, _ a: Selector?, _ k: String, _ mods: NSEvent.ModifierFlags = .command, target: AnyObject? = nil) -> NSMenuItem {
            let i = NSMenuItem(title: t, action: a, keyEquivalent: k); i.keyEquivalentModifierMask = mods; i.target = target; return i
        }
        sub("Pult", [
            item("About Pult", #selector(NSApplication.orderFrontStandardAboutPanel(_:)), ""),
            .separator(),
            item("Hide Pult", #selector(NSApplication.hide(_:)), "h"),
            item("Hide Others", #selector(NSApplication.hideOtherApplications(_:)), "h", [.command, .option]),
            .separator(),
            item("Quit Pult", #selector(NSApplication.terminate(_:)), "q"),
        ])
        sub("Edit", [
            item("Undo", Selector(("undo:")), "z"),
            item("Redo", Selector(("redo:")), "z", [.command, .shift]),
            .separator(),
            item("Cut", #selector(NSText.cut(_:)), "x"),
            item("Copy", #selector(NSText.copy(_:)), "c"),
            item("Paste", #selector(NSText.paste(_:)), "v"),
            item("Select All", #selector(NSText.selectAll(_:)), "a"),
        ])
        sub("View", [
            item("Reload", #selector(reload(_:)), "r", target: self),
            item("Open in Browser", #selector(openInBrowser(_:)), "o", [.command, .shift], target: self),
            .separator(),
            item("Actual Size", #selector(zoomReset(_:)), "0", target: self),
            item("Zoom In", #selector(zoomIn(_:)), "=", target: self),
            item("Zoom Out", #selector(zoomOut(_:)), "-", target: self),
            .separator(),
            item("Enter Full Screen", #selector(NSWindow.toggleFullScreen(_:)), "f", [.command, .control]),
        ])
        sub("Window", [
            item("Minimize", #selector(NSWindow.performMiniaturize(_:)), "m"),
            item("Close", #selector(NSWindow.performClose(_:)), "w"),
        ])
        NSApp.mainMenu = main
    }
}

let app = NSApplication.shared
let delegate = Pult()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
