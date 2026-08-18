// ocrtext: recognize text in a PDF or image using Apple's Vision framework.
//
// Usage: ocrtext <file.pdf|image>
// Prints recognized text to stdout, pages separated by a form-feed (\f) line.
// Runs entirely on-device (this is the engine behind Live Text, so it handles
// handwriting); exits non-zero with a message on stderr if the file can't be read.

import AppKit
import Foundation
import PDFKit
import Vision

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data(("ocrtext: " + message + "\n").utf8))
    exit(1)
}

func recognize(_ cgImage: CGImage) -> String {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    request.recognitionLanguages = ["en-US"]
    let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
    do {
        try handler.perform([request])
    } catch {
        return ""
    }
    let lines = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    return lines.joined(separator: "\n")
}

func cgImage(from nsImage: NSImage) -> CGImage? {
    nsImage.cgImage(forProposedRect: nil, context: nil, hints: nil)
}

guard CommandLine.arguments.count == 2 else {
    fail("usage: ocrtext <file.pdf|image>")
}
let url = URL(fileURLWithPath: CommandLine.arguments[1])
guard FileManager.default.fileExists(atPath: url.path) else {
    fail("no such file: \(url.path)")
}

var pages: [String] = []

if url.pathExtension.lowercased() == "pdf" {
    guard let doc = PDFDocument(url: url) else {
        fail("could not open PDF: \(url.path)")
    }
    // Rasterize at ~300 DPI (PDF points are 72/inch) so small handwriting survives.
    let scale: CGFloat = 300.0 / 72.0
    for i in 0..<doc.pageCount {
        guard let page = doc.page(at: i) else {
            pages.append("")
            continue
        }
        let bounds = page.bounds(for: .mediaBox)
        let size = CGSize(width: bounds.width * scale, height: bounds.height * scale)
        let image = page.thumbnail(of: size, for: .mediaBox)
        pages.append(cgImage(from: image).map(recognize) ?? "")
    }
} else {
    guard let image = NSImage(contentsOf: url), let cg = cgImage(from: image) else {
        fail("could not read image: \(url.path)")
    }
    pages.append(recognize(cg))
}

print(pages.joined(separator: "\n\u{0C}\n"))
