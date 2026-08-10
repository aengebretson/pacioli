#pragma once

namespace luca::detail {

#if (defined(__GNUC__) || defined(__clang__)) && defined(__SIZEOF_INT128__)
using Wide = __int128;
static_assert(sizeof(Wide) == 16, "LUCA requires a 128-bit widened integer");
static_assert(Wide{-1} < Wide{0}, "LUCA requires a signed widened integer");
#else
#error "LUCA fixed-point arithmetic requires compiler support for a signed 128-bit integer (__int128); GCC and Clang are currently supported"
#endif

}  // namespace luca::detail
