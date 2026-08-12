// audiocap — capture macOS system audio (Core Audio process tap) + microphone to WAV files.
//
// Usage: audiocap <output-dir> [--max-seconds N] [--no-mic] [--no-system]
//
// Writes <output-dir>/system.wav and <output-dir>/mic.wav until SIGINT/SIGTERM
// (or --max-seconds elapses), then finalizes the files and exits.
//
// Requires macOS 14.4+ (Core Audio process taps). The first run prompts for
// System Audio Recording and Microphone permission (granted to the parent
// terminal app).

import Foundation
import CoreAudio
import AudioToolbox
import AVFoundation

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(("audiocap: " + message + "\n").data(using: .utf8)!)
    exit(1)
}

func checkErr(_ status: OSStatus, _ what: String) {
    if status != noErr {
        fail("\(what) failed (OSStatus \(status)). If this is a permission error, grant System Audio Recording / Microphone access to your terminal in System Settings > Privacy & Security.")
    }
}

func log(_ message: String) {
    print(message)
    fflush(stdout)
}

// MARK: - Argument parsing

var outputDir: String? = nil
var maxSeconds: Double? = nil
var captureMic = true
var captureSystem = true

var args = Array(CommandLine.arguments.dropFirst())
while !args.isEmpty {
    let arg = args.removeFirst()
    switch arg {
    case "--max-seconds":
        guard !args.isEmpty, let n = Double(args.removeFirst()) else { fail("--max-seconds requires a number") }
        maxSeconds = n
    case "--no-mic":
        captureMic = false
    case "--no-system":
        captureSystem = false
    case "-h", "--help":
        print("usage: audiocap <output-dir> [--max-seconds N] [--no-mic] [--no-system]")
        exit(0)
    default:
        if outputDir == nil { outputDir = arg } else { fail("unexpected argument: \(arg)") }
    }
}

guard let outDir = outputDir else { fail("usage: audiocap <output-dir> [--max-seconds N] [--no-mic] [--no-system]") }
try? FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)
let outURL = URL(fileURLWithPath: outDir, isDirectory: true)

// MARK: - System audio capture via Core Audio process tap

final class SystemAudioRecorder {
    private var tapID = AudioObjectID(kAudioObjectUnknown)
    private var aggregateID = AudioObjectID(kAudioObjectUnknown)
    private var ioProcID: AudioDeviceIOProcID?
    private var file: AVAudioFile?
    private let queue = DispatchQueue(label: "audiocap.system-io")

    func start(fileURL: URL) throws {
        // Tap all system audio output (a global tap excluding no processes).
        let description = CATapDescription(stereoGlobalTapButExcludeProcesses: [])
        description.uuid = UUID()
        description.muteBehavior = .unmuted
        description.isPrivate = true

        checkErr(AudioHardwareCreateProcessTap(description, &tapID), "creating system audio tap")

        // Read the tap's stream format.
        var asbd = AudioStreamBasicDescription()
        var size = UInt32(MemoryLayout<AudioStreamBasicDescription>.size)
        var formatAddress = AudioObjectPropertyAddress(
            mSelector: kAudioTapPropertyFormat,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain)
        checkErr(AudioObjectGetPropertyData(tapID, &formatAddress, 0, nil, &size, &asbd), "reading tap format")

        guard let format = AVAudioFormat(streamDescription: &asbd) else {
            fail("could not build AVAudioFormat from tap stream description")
        }

        // Find the default system output device UID (the aggregate needs a real device).
        var outputDeviceID = AudioObjectID(kAudioObjectUnknown)
        size = UInt32(MemoryLayout<AudioObjectID>.size)
        var defaultOutputAddress = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultSystemOutputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain)
        checkErr(AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &defaultOutputAddress, 0, nil, &size, &outputDeviceID),
                 "finding default output device")

        var uidAddress = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyDeviceUID,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain)
        var outputUID: CFString = "" as CFString
        size = UInt32(MemoryLayout<CFString>.size)
        checkErr(withUnsafeMutablePointer(to: &outputUID) { ptr in
            AudioObjectGetPropertyData(outputDeviceID, &uidAddress, 0, nil, &size, ptr)
        }, "reading output device UID")

        // Private aggregate device wrapping the default output + our tap.
        let aggregateUID = UUID().uuidString
        let aggregateDescription: [String: Any] = [
            kAudioAggregateDeviceNameKey: "audiocap-\(aggregateUID)",
            kAudioAggregateDeviceUIDKey: aggregateUID,
            kAudioAggregateDeviceMainSubDeviceKey: outputUID,
            kAudioAggregateDeviceIsPrivateKey: true,
            kAudioAggregateDeviceIsStackedKey: false,
            kAudioAggregateDeviceTapAutoStartKey: true,
            kAudioAggregateDeviceSubDeviceListKey: [
                [kAudioSubDeviceUIDKey: outputUID]
            ],
            kAudioAggregateDeviceTapListKey: [
                [
                    kAudioSubTapDriftCompensationKey: true,
                    kAudioSubTapUIDKey: description.uuid.uuidString,
                ]
            ],
        ]
        checkErr(AudioHardwareCreateAggregateDevice(aggregateDescription as CFDictionary, &aggregateID),
                 "creating aggregate device")

        let audioFile = try AVAudioFile(
            forWriting: fileURL,
            settings: format.settings,
            commonFormat: format.commonFormat,
            interleaved: format.isInterleaved)
        file = audioFile

        checkErr(AudioDeviceCreateIOProcIDWithBlock(&ioProcID, aggregateID, queue) { _, inInputData, _, _, _ in
            guard let buffer = AVAudioPCMBuffer(pcmFormat: format, bufferListNoCopy: inInputData, deallocator: nil) else { return }
            do {
                try audioFile.write(from: buffer)
            } catch {
                FileHandle.standardError.write("audiocap: system audio write error: \(error)\n".data(using: .utf8)!)
            }
        }, "creating IO proc")

        checkErr(AudioDeviceStart(aggregateID, ioProcID), "starting aggregate device")
    }

    func stop() {
        if aggregateID != kAudioObjectUnknown, let proc = ioProcID {
            AudioDeviceStop(aggregateID, proc)
            AudioDeviceDestroyIOProcID(aggregateID, proc)
            ioProcID = nil
        }
        if aggregateID != kAudioObjectUnknown {
            AudioHardwareDestroyAggregateDevice(aggregateID)
            aggregateID = AudioObjectID(kAudioObjectUnknown)
        }
        if tapID != kAudioObjectUnknown {
            AudioHardwareDestroyProcessTap(tapID)
            tapID = AudioObjectID(kAudioObjectUnknown)
        }
        file = nil // finalize WAV header
    }
}

// MARK: - Microphone capture via AVAudioEngine

final class MicRecorder {
    private let engine = AVAudioEngine()
    private var file: AVAudioFile?

    func start(fileURL: URL) throws {
        // Ensure the mic permission prompt fires before the engine starts.
        let semaphore = DispatchSemaphore(value: 0)
        var granted = false
        AVCaptureDevice.requestAccess(for: .audio) { ok in
            granted = ok
            semaphore.signal()
        }
        semaphore.wait()
        guard granted else {
            fail("microphone access denied. Grant Microphone access to your terminal in System Settings > Privacy & Security.")
        }

        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        let audioFile = try AVAudioFile(
            forWriting: fileURL,
            settings: format.settings,
            commonFormat: format.commonFormat,
            interleaved: format.isInterleaved)
        file = audioFile

        input.installTap(onBus: 0, bufferSize: 4096, format: format) { buffer, _ in
            do {
                try audioFile.write(from: buffer)
            } catch {
                FileHandle.standardError.write("audiocap: mic write error: \(error)\n".data(using: .utf8)!)
            }
        }
        try engine.start()
    }

    func stop() {
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        file = nil // finalize WAV header
    }
}

// MARK: - Main

let systemRecorder = SystemAudioRecorder()
let micRecorder = MicRecorder()

if captureSystem {
    do {
        try systemRecorder.start(fileURL: outURL.appendingPathComponent("system.wav"))
        log("SYSTEM " + outURL.appendingPathComponent("system.wav").path)
    } catch {
        fail("failed to start system audio capture: \(error)")
    }
}

if captureMic {
    do {
        try micRecorder.start(fileURL: outURL.appendingPathComponent("mic.wav"))
        log("MIC " + outURL.appendingPathComponent("mic.wav").path)
    } catch {
        fail("failed to start microphone capture: \(error)")
    }
}

log("READY")

var shouldStop = false
let stopLock = NSCondition()

func requestStop() {
    stopLock.lock()
    shouldStop = true
    stopLock.signal()
    stopLock.unlock()
}

signal(SIGINT, SIG_IGN)
signal(SIGTERM, SIG_IGN)
let sigintSource = DispatchSource.makeSignalSource(signal: SIGINT, queue: .main)
sigintSource.setEventHandler { requestStop() }
sigintSource.resume()
let sigtermSource = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)
sigtermSource.setEventHandler { requestStop() }
sigtermSource.resume()

if let seconds = maxSeconds {
    DispatchQueue.global().asyncAfter(deadline: .now() + seconds) { requestStop() }
}

// Wait for a stop request on a background thread; signal sources fire on the main queue.
DispatchQueue.global().async {
    stopLock.lock()
    while !shouldStop { stopLock.wait() }
    stopLock.unlock()

    if captureSystem { systemRecorder.stop() }
    if captureMic { micRecorder.stop() }
    log("DONE")
    exit(0)
}

RunLoop.main.run()
