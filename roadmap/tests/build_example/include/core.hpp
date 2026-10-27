#pragma once
#include <span>
int twice(int value);
// The public declaration requires consumers to use C++20.
inline int first(std::span<const int> values) { return values.front(); }
