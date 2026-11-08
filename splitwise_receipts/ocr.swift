import Foundation
import Vision
import AppKit
let url = URL(fileURLWithPath: CommandLine.arguments[1])
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
try VNImageRequestHandler(url: url).perform([request])
let results = request.results ?? []
// Cluster text boxes into receipt rows so right-aligned prices follow their labels.
var rows: [[VNRecognizedTextObservation]] = []
for observation in results.sorted(by: { $0.boundingBox.midY > $1.boundingBox.midY }) {
    if let index = rows.firstIndex(where: { abs($0[0].boundingBox.midY - observation.boundingBox.midY) < min($0[0].boundingBox.height, observation.boundingBox.height) * 0.6 }) {
        rows[index].append(observation)
    } else { rows.append([observation]) }
}
for row in rows {
    print(row.sorted(by: {$0.boundingBox.minX < $1.boundingBox.minX}).compactMap {$0.topCandidates(1).first?.string}.joined(separator: " "))
}
