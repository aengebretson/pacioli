#pragma once

#include "luca/core/values.hpp"

#include <array>
#include <bit>
#include <charconv>
#include <cstddef>
#include <cstdint>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace luca::serialization {

using CanonicalBytes = std::vector<std::byte>;

namespace detail {

inline void append_octet(CanonicalBytes &output, std::uint8_t value) {
  output.push_back(static_cast<std::byte>(value));
}

inline void append_u32(CanonicalBytes &output, std::uint32_t value) {
  append_octet(output, static_cast<std::uint8_t>(value >> 24));
  append_octet(output, static_cast<std::uint8_t>(value >> 16));
  append_octet(output, static_cast<std::uint8_t>(value >> 8));
  append_octet(output, static_cast<std::uint8_t>(value));
}

inline void append_ascii(CanonicalBytes &output, std::string_view value) {
  for (const char character : value)
    append_octet(output, static_cast<std::uint8_t>(static_cast<unsigned char>(character)));
}

inline void append_text(CanonicalBytes &output, std::string_view value) {
  append_octet(output, 0x04);
  append_u32(output, static_cast<std::uint32_t>(value.size()));
  append_ascii(output, value);
}

inline void append_key(CanonicalBytes &output, std::string_view key) {
  append_u32(output, static_cast<std::uint32_t>(key.size()));
  append_ascii(output, key);
}

inline std::string canonical_decimal(std::int64_t value) {
  std::array<char, 32> buffer{};
  const auto [end, error] = std::to_chars(buffer.data(), buffer.data() + buffer.size(), value);
  (void)error; // A 32-byte buffer holds every signed 64-bit decimal representation.
  return {buffer.data(), end};
}

inline CanonicalBytes fixed_point_bytes(std::string_view schema_version, std::string_view scale,
                                        std::int64_t scaled_value) {
  CanonicalBytes output;
  output.reserve(128);
  append_ascii(output, "LCB1");
  append_octet(output, 0x06);
  append_u32(output, 3);

  // LCB1 maps are ordered by the raw UTF-8 bytes of their keys.
  append_key(output, "scale");
  append_text(output, scale);
  append_key(output, "scaled_value");
  append_text(output, canonical_decimal(scaled_value));
  append_key(output, "schema_version");
  append_text(output, schema_version);
  return output;
}

inline constexpr std::array<std::uint32_t, 64> sha256_round_constants{
    0x428a2f98U, 0x71374491U, 0xb5c0fbcfU, 0xe9b5dba5U, 0x3956c25bU, 0x59f111f1U, 0x923f82a4U,
    0xab1c5ed5U, 0xd807aa98U, 0x12835b01U, 0x243185beU, 0x550c7dc3U, 0x72be5d74U, 0x80deb1feU,
    0x9bdc06a7U, 0xc19bf174U, 0xe49b69c1U, 0xefbe4786U, 0x0fc19dc6U, 0x240ca1ccU, 0x2de92c6fU,
    0x4a7484aaU, 0x5cb0a9dcU, 0x76f988daU, 0x983e5152U, 0xa831c66dU, 0xb00327c8U, 0xbf597fc7U,
    0xc6e00bf3U, 0xd5a79147U, 0x06ca6351U, 0x14292967U, 0x27b70a85U, 0x2e1b2138U, 0x4d2c6dfcU,
    0x53380d13U, 0x650a7354U, 0x766a0abbU, 0x81c2c92eU, 0x92722c85U, 0xa2bfe8a1U, 0xa81a664bU,
    0xc24b8b70U, 0xc76c51a3U, 0xd192e819U, 0xd6990624U, 0xf40e3585U, 0x106aa070U, 0x19a4c116U,
    0x1e376c08U, 0x2748774cU, 0x34b0bcb5U, 0x391c0cb3U, 0x4ed8aa4aU, 0x5b9cca4fU, 0x682e6ff3U,
    0x748f82eeU, 0x78a5636fU, 0x84c87814U, 0x8cc70208U, 0x90befffaU, 0xa4506cebU, 0xbef9a3f7U,
    0xc67178f2U};

inline std::uint32_t load_u32(const std::byte *input) {
  return (static_cast<std::uint32_t>(std::to_integer<std::uint8_t>(input[0])) << 24) |
         (static_cast<std::uint32_t>(std::to_integer<std::uint8_t>(input[1])) << 16) |
         (static_cast<std::uint32_t>(std::to_integer<std::uint8_t>(input[2])) << 8) |
         static_cast<std::uint32_t>(std::to_integer<std::uint8_t>(input[3]));
}

inline void sha256_compress(std::array<std::uint32_t, 8> &state, const std::byte *block) {
  std::array<std::uint32_t, 64> words{};
  for (std::size_t index = 0; index < 16; ++index) {
    words[index] = load_u32(block + (index * 4));
  }
  for (std::size_t index = 16; index < words.size(); ++index) {
    const auto sigma0 = std::rotr(words[index - 15], 7) ^ std::rotr(words[index - 15], 18) ^
                        (words[index - 15] >> 3);
    const auto sigma1 = std::rotr(words[index - 2], 17) ^ std::rotr(words[index - 2], 19) ^
                        (words[index - 2] >> 10);
    words[index] = words[index - 16] + sigma0 + words[index - 7] + sigma1;
  }

  auto a = state[0];
  auto b = state[1];
  auto c = state[2];
  auto d = state[3];
  auto e = state[4];
  auto f = state[5];
  auto g = state[6];
  auto h = state[7];

  for (std::size_t index = 0; index < words.size(); ++index) {
    const auto choice = (e & f) ^ ((~e) & g);
    const auto majority = (a & b) ^ (a & c) ^ (b & c);
    const auto sum0 = std::rotr(a, 2) ^ std::rotr(a, 13) ^ std::rotr(a, 22);
    const auto sum1 = std::rotr(e, 6) ^ std::rotr(e, 11) ^ std::rotr(e, 25);
    const auto temporary1 = h + sum1 + choice + sha256_round_constants[index] + words[index];
    const auto temporary2 = sum0 + majority;
    h = g;
    g = f;
    f = e;
    e = d + temporary1;
    d = c;
    c = b;
    b = a;
    a = temporary1 + temporary2;
  }

  state[0] += a;
  state[1] += b;
  state[2] += c;
  state[3] += d;
  state[4] += e;
  state[5] += f;
  state[6] += g;
  state[7] += h;
}

inline std::array<std::byte, 32> sha256(std::span<const std::byte> input) {
  std::array<std::uint32_t, 8> state{0x6a09e667U, 0xbb67ae85U, 0x3c6ef372U, 0xa54ff53aU,
                                     0x510e527fU, 0x9b05688cU, 0x1f83d9abU, 0x5be0cd19U};

  std::size_t offset = 0;
  while (input.size() - offset >= 64) {
    sha256_compress(state, input.data() + offset);
    offset += 64;
  }

  std::array<std::byte, 128> tail{};
  const auto remainder = input.size() - offset;
  for (std::size_t index = 0; index < remainder; ++index)
    tail[index] = input[offset + index];
  tail[remainder] = std::byte{0x80};

  const std::uint64_t bit_length = static_cast<std::uint64_t>(input.size()) * 8U;
  const std::size_t tail_size = remainder < 56 ? 64 : 128;
  for (std::size_t index = 0; index < 8; ++index) {
    tail[tail_size - 1 - index] = static_cast<std::byte>(bit_length >> (index * 8));
  }
  sha256_compress(state, tail.data());
  if (tail_size == 128)
    sha256_compress(state, tail.data() + 64);

  std::array<std::byte, 32> digest{};
  for (std::size_t index = 0; index < state.size(); ++index) {
    digest[index * 4] = static_cast<std::byte>(state[index] >> 24);
    digest[index * 4 + 1] = static_cast<std::byte>(state[index] >> 16);
    digest[index * 4 + 2] = static_cast<std::byte>(state[index] >> 8);
    digest[index * 4 + 3] = static_cast<std::byte>(state[index]);
  }
  return digest;
}

inline std::string sha256_hex(std::span<const std::byte> input) {
  constexpr std::string_view digits = "0123456789abcdef";
  const auto digest = sha256(input);
  std::string output;
  output.reserve(digest.size() * 2);
  for (const auto octet : digest) {
    const auto value = std::to_integer<std::uint8_t>(octet);
    output.push_back(digits[value >> 4]);
    output.push_back(digits[value & 0x0f]);
  }
  return output;
}

} // namespace detail

[[nodiscard]] inline CanonicalBytes canonical_bytes(const Money &value) {
  CanonicalBytes output;
  output.reserve(144);
  detail::append_ascii(output, "LCB1");
  detail::append_octet(output, 0x06);
  detail::append_u32(output, 4);

  detail::append_key(output, "currency");
  detail::append_text(output, value.currency().code());
  detail::append_key(output, "scale");
  detail::append_text(output, "6");
  detail::append_key(output, "scaled_value");
  detail::append_text(output, detail::canonical_decimal(value.scaled_value()));
  detail::append_key(output, "schema_version");
  detail::append_text(output, "luca.money.v1");
  return output;
}

[[nodiscard]] inline CanonicalBytes canonical_bytes(const Quantity &value) {
  return detail::fixed_point_bytes("luca.quantity.v1", "8", value.scaled_value());
}

[[nodiscard]] inline CanonicalBytes canonical_bytes(const Price &value) {
  return detail::fixed_point_bytes("luca.price.v1", "8", value.scaled_value());
}

[[nodiscard]] inline std::string canonical_digest(const Money &value) {
  return detail::sha256_hex(canonical_bytes(value));
}

[[nodiscard]] inline std::string canonical_digest(const Quantity &value) {
  return detail::sha256_hex(canonical_bytes(value));
}

[[nodiscard]] inline std::string canonical_digest(const Price &value) {
  return detail::sha256_hex(canonical_bytes(value));
}

} // namespace luca::serialization
