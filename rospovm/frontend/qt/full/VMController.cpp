#include "VMController.h"

#include "Binary.h"

#include <QFile>
#include <QRegularExpression>
#include <QTextStream>
#include <utility>

namespace {

constexpr uint32_t kSourceLineSearchRadius = 32;

QString normalizeSourceLine(const QString &line)
{
    QString normalized = line;
    normalized.replace('\t', ' ');
    normalized.replace(QRegularExpression(" +"), " ");
    return normalized.simplified();
}

bool tryResolveNearbySourceLine(
    const QString &sourceFilePath,
    uint32_t suggestedLine,
    const QString &expectedLineContent,
    uint32_t &resolvedLine)
{
    const QString normalizedExpected = normalizeSourceLine(expectedLineContent);
    if (normalizedExpected.isEmpty()) {
        return false;
    }

    QFile sourceFile(sourceFilePath);
    if (!sourceFile.open(QIODevice::ReadOnly | QIODevice::Text)) {
        return false;
    }

    QTextStream stream(&sourceFile);
    QStringList lines;
    while (!stream.atEnd()) {
        lines.append(stream.readLine());
    }

    if (lines.isEmpty()) {
        return false;
    }

    const uint32_t lineCount = static_cast<uint32_t>(lines.size());
    uint32_t centerLine = suggestedLine;
    if (centerLine == 0) {
        centerLine = 1;
    } else if (centerLine > lineCount) {
        centerLine = lineCount;
    }

    const auto lineMatches = [&](uint32_t oneBasedLine) -> bool {
        if (oneBasedLine == 0 || oneBasedLine > lineCount) {
            return false;
        }
        const QString sourceLine = lines.at(static_cast<int>(oneBasedLine - 1));
        const QString normalizedSource = normalizeSourceLine(sourceLine);
        return normalizedSource == normalizedExpected;
    };

    bool found = false;
    uint32_t bestLine = 0;
    uint32_t bestDistance = 0;

    for (uint32_t offset = 0; offset <= kSourceLineSearchRadius; ++offset) {
        if (centerLine > offset) {
            const uint32_t upLine = centerLine - offset;
            if (lineMatches(upLine)) {
                if (!found || offset < bestDistance) {
                    found = true;
                    bestLine = upLine;
                    bestDistance = offset;
                }
            }
        }

        if (offset == 0) {
            continue;
        }

        const uint32_t downLine = centerLine + offset;
        if (downLine <= lineCount && lineMatches(downLine)) {
            if (!found || offset < bestDistance) {
                found = true;
                bestLine = downLine;
                bestDistance = offset;
            }
        }
    }

    if (!found) {
        return false;
    }

    resolvedLine = bestLine;
    return true;
}

} // namespace

VMController::VMController(QObject *parent)
    : VMControllerCore(parent)
{
}

VMController::~VMController() = default;

QString VMController::getRegisterAllocationTooltip(int index) const
{
    try {
        const uint32_t pc = vmInstance()->getProgramCounter();
        const RegisterAllocationInfo *alloc = vmInstance()->getRegisterAllocation(pc, index);
        if (!alloc) {
            return QString();
        }

        QString kind = QString::fromStdString(alloc->var_kind);
        if (kind.isEmpty()) {
            kind = "local";
        }
        QString text = QString("%1 (%2)")
                           .arg(QString::fromStdString(alloc->variable_name), kind);

        const QString type = QString::fromStdString(alloc->variable_type);
        if (!type.isEmpty()) {
            text += QString("\nType: %1").arg(type);
        }

        const QString origin = QString::fromStdString(alloc->origin);
        if (!origin.isEmpty()) {
            text += QString("\nOrigin: %1").arg(origin);
        }

        if (kind == "temp") {
            text += "\nTemporary calculation";
        }

        return text;
    } catch (...) {
        return QString();
    }
}

QString VMController::getRegisterAllocationTooltipAt(uint32_t address, int index) const
{
    try {
        const RegisterAllocationInfo *alloc = vmInstance()->getRegisterAllocation(address, index);
        if (!alloc) {
            return QString();
        }

        QString kind = QString::fromStdString(alloc->var_kind);
        if (kind.isEmpty()) {
            kind = "local";
        }
        QString text = QString("%1 (%2)")
                           .arg(QString::fromStdString(alloc->variable_name), kind);

        const QString type = QString::fromStdString(alloc->variable_type);
        if (!type.isEmpty()) {
            text += QString("\nType: %1").arg(type);
        }

        const QString origin = QString::fromStdString(alloc->origin);
        if (!origin.isEmpty()) {
            text += QString("\nOrigin: %1").arg(origin);
        }

        if (kind == "temp") {
            text += "\nTemporary calculation";
        }

        return text;
    } catch (...) {
        return QString();
    }
}

QString VMController::getCurrentSourceLocation() const
{
    return getSourceLocation(vmInstance()->getProgramCounter());
}

QString VMController::getCurrentOriginalInstruction() const
{
    std::string text = vmInstance()->getOriginalInstruction(vmInstance()->getProgramCounter());
    return QString::fromStdString(text);
}

QString VMController::getSourceLocation(uint32_t address) const
{
    QString filePath;
    uint32_t line = 0;
    if (getSourceReference(address, filePath, line)) {
        return QString("%1:%2").arg(filePath).arg(line);
    }

    std::string location = vmInstance()->formatSourceLocation(address);
    return QString::fromStdString(location);
}

bool VMController::getSourceReference(uint32_t address, QString &filePath, uint32_t &line) const
{
    const DebugEntry *entry = vmInstance()->getDebugInfo(address);
    if (!entry) {
        return false;
    }

    std::shared_ptr<Binary> loadedBinary = vmInstance()->getLoadedBinary();
    if (!loadedBinary || loadedBinary->debug_map.empty()) {
        return false;
    }

    for (const auto &debugPair : loadedBinary->debug_map) {
        const auto &debugInfo = debugPair.second;
        auto fileIt = debugInfo->file_table.find(entry->file_id);
        if (fileIt != debugInfo->file_table.end()) {
            filePath = QString::fromStdString(fileIt->second);
            line = entry->line;

            uint32_t resolvedLine = 0;
            if (tryResolveNearbySourceLine(
                    filePath,
                    line,
                    QString::fromStdString(entry->original_text),
                    resolvedLine)) {
                line = resolvedLine;
            }

            return true;
        }
    }

    return false;
}

bool VMController::getMallocHeapSnapshot(MallocHeapSnapshot &snapshot) const
{
    const auto *vm = vmInstance();
    if (!vm) {
        return false;
    }

    const auto binary = vm->getLoadedBinary();
    if (!binary) {
        return false;
    }

    std::map<std::string, uint32_t> symbols;
    for (const auto &debugPair : binary->debug_map) {
        if (debugPair.second) {
            symbols.insert(debugPair.second->symbols.begin(), debugPair.second->symbols.end());
        }
    }

    const auto heapIt = symbols.find("__heap_area");
    const auto usedIt = symbols.find("__heap_used");
    const auto headIt = symbols.find("malloc_head");
    const auto sizeIt = symbols.find("__heap_area_size");
    if (heapIt == symbols.end() || usedIt == symbols.end() || headIt == symbols.end() || sizeIt == symbols.end()) {
        return false;
    }

    MallocHeapSnapshot result;
    result.baseAddress = heapIt->second;
    result.size = sizeIt->second;
    result.used = vm->readMemory(usedIt->second);
    if (result.size == 0 || result.size > (1u << 20) || result.used > result.size) {
        return false;
    }

    const uint64_t heapEnd = static_cast<uint64_t>(result.baseAddress) + result.size;
    uint32_t header = vm->readMemory(headIt->second);
    const size_t maxBlocks = result.size / 16 + 1;
    for (size_t i = 0; header != 0 && i < maxBlocks; ++i) {
        const uint64_t headerEnd = static_cast<uint64_t>(header) + 16;
        if (header < result.baseAddress || headerEnd > heapEnd) {
            return false;
        }

        const uint32_t blockSize = vm->readMemory(header);
        const uint32_t isFree = vm->readMemory(header + 4);
        const uint32_t exists = vm->readMemory(header + 8);
        const uint32_t next = vm->readMemory(header + 12);
        if (exists == 0) {
            header = 0;
            break;
        }
        if (blockSize > heapEnd - headerEnd) {
            return false;
        }
        if (blockSize != 0) {
            result.blocks.push_back({header, static_cast<uint32_t>(headerEnd), blockSize, isFree != 0});
        }
        header = next;
    }
    if (header != 0) {
        return false;
    }

    snapshot = std::move(result);
    return true;
}
