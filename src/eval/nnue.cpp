#include "nnue.h"
#include <algorithm>
#include <fstream>
#include <limits>
#include <stdexcept>

namespace chessbot {
namespace {
void expect(std::istream &input, std::string_view expected) {
    std::string token;
    if (!(input >> token) || token != expected)
        throw std::invalid_argument("NNUE: expected " + std::string(expected));
}
template <typename Target>
Target readInteger(std::istream &input, std::string_view field, std::int64_t minimum,
                   std::int64_t maximum) {
    std::int64_t value = 0;
    if (!(input >> value) || value < minimum || value > maximum)
        throw std::invalid_argument("NNUE: invalid " + std::string(field));
    return static_cast<Target>(value);
}
} // namespace

int NnueNetwork::feature(Piece piece, Square square) {
    return (static_cast<int>(piece.color) * 6 + static_cast<int>(piece.type)) * 64 + square;
}

void NnueNetwork::load(const std::string &path) {
    std::ifstream input(path);
    if (!input)
        throw std::invalid_argument("NNUE: cannot open file: " + path);
    expect(input, "CHESSBOT_NNUE");
    if (readInteger<int>(input, "format version", 1, 1) != 1)
        throw std::invalid_argument("NNUE: unsupported format version");
    expect(input, "version");
    std::string version;
    if (!(input >> version) || version.empty())
        throw std::invalid_argument("NNUE: missing network version");
    expect(input, "architecture");
    std::string architecture;
    input >> architecture;
    expect(input, "hidden_size");
    const int hiddenSize = readInteger<int>(input, "hidden size", 1, NnueMaximumHidden);
    if (architecture != "sparse_768x" + std::to_string(hiddenSize) + "_relu_1")
        throw std::invalid_argument("NNUE: architecture does not match hidden size");
    expect(input, "input_quant");
    const int inputQuant = readInteger<int>(input, "input quantization", 1, 32768);
    expect(input, "output_quant");
    const int outputQuant = readInteger<int>(input, "output quantization", 1, 32768);
    expect(input, "hidden_bias");
    std::vector<std::int32_t> hiddenBias(hiddenSize);
    for (auto &value : hiddenBias)
        value = readInteger<std::int32_t>(input, "hidden bias", -100'000'000, 100'000'000);
    expect(input, "input_weights");
    std::vector<std::int16_t> inputWeights(NnueInputSize * hiddenSize);
    for (auto &value : inputWeights)
        value = readInteger<std::int16_t>(input, "input weight",
                                          std::numeric_limits<std::int16_t>::min(),
                                          std::numeric_limits<std::int16_t>::max());
    expect(input, "output_bias");
    const auto outputBias =
        readInteger<std::int64_t>(input, "output bias", -10'000'000'000LL, 10'000'000'000LL);
    expect(input, "output_weights");
    std::vector<std::int16_t> outputWeights(hiddenSize);
    for (auto &value : outputWeights)
        value = readInteger<std::int16_t>(input, "output weight",
                                          std::numeric_limits<std::int16_t>::min(),
                                          std::numeric_limits<std::int16_t>::max());
    expect(input, "END");
    std::string trailing;
    if (input >> trailing)
        throw std::invalid_argument("NNUE: trailing data after END");
    version_ = std::move(version);
    hiddenSize_ = hiddenSize;
    inputQuant_ = inputQuant;
    outputQuant_ = outputQuant;
    hiddenBias_ = std::move(hiddenBias);
    inputWeights_ = std::move(inputWeights);
    outputWeights_ = std::move(outputWeights);
    outputBias_ = outputBias;
}

std::size_t NnueNetwork::memoryBytes() const {
    return hiddenBias_.size() * sizeof(hiddenBias_[0]) +
           inputWeights_.size() * sizeof(inputWeights_[0]) +
           outputWeights_.size() * sizeof(outputWeights_[0]) + sizeof(outputBias_);
}

void NnueNetwork::addFeature(NnueAccumulator &accumulator, Piece piece, Square square,
                             int sign) const {
    if (piece.type == None)
        return;
    const auto offset = static_cast<std::size_t>(feature(piece, square) * hiddenSize_);
    for (int index = 0; index < hiddenSize_; ++index)
        accumulator.values[index] += sign * inputWeights_[offset + index];
}

NnueAccumulator NnueNetwork::refresh(const Board &board) const {
    if (!loaded())
        throw std::logic_error("NNUE: no network loaded");
    NnueAccumulator accumulator;
    accumulator.size = hiddenSize_;
    std::copy(hiddenBias_.begin(), hiddenBias_.end(), accumulator.values.begin());
    for (Square square = 0; square < 64; ++square)
        addFeature(accumulator, board.at(square), square, 1);
    return accumulator;
}

void NnueNetwork::updateAfterMove(NnueAccumulator &accumulator, const Board &after, Move move,
                                  const StateInfo &state) const {
    if (accumulator.size != hiddenSize_)
        throw std::invalid_argument("NNUE: accumulator belongs to another network");
    const Color movingColor = opposite(after.sideToMove());
    addFeature(accumulator, {move.moving(), movingColor}, move.from(), -1);
    if (state.captured.type != None) {
        const Square capturedSquare =
            move.has(EnPassant) ? move.to() + (movingColor == White ? -8 : 8) : move.to();
        addFeature(accumulator, state.captured, capturedSquare, -1);
    }
    const PieceType placed = move.promotion() == None ? move.moving() : move.promotion();
    addFeature(accumulator, {placed, movingColor}, move.to(), 1);
    if (move.has(Castle)) {
        const bool kingSide = move.to() > move.from();
        const Square rookFrom = (movingColor == White ? 0 : 56) + (kingSide ? 7 : 0);
        const Square rookTo = move.from() + (kingSide ? 1 : -1);
        addFeature(accumulator, {Rook, movingColor}, rookFrom, -1);
        addFeature(accumulator, {Rook, movingColor}, rookTo, 1);
    }
}

Score NnueNetwork::evaluate(const Board &board, const NnueAccumulator &accumulator) const {
    if (accumulator.size != hiddenSize_)
        throw std::invalid_argument("NNUE: accumulator belongs to another network");
    std::int64_t output = outputBias_;
    for (int index = 0; index < hiddenSize_; ++index)
        output += static_cast<std::int64_t>(std::max<std::int32_t>(0, accumulator.values[index])) *
                  outputWeights_[index];
    const auto divisor = static_cast<std::int64_t>(inputQuant_) * outputQuant_;
    const auto whiteScore = std::clamp<std::int64_t>(output / divisor, -30'000, 30'000);
    return static_cast<Score>(board.sideToMove() == White ? whiteScore : -whiteScore);
}
} // namespace chessbot
