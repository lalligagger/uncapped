#include <assert.h>
#include <stdint.h>

#include "card_abstraction.hpp"

static void check_round_counts() {
  State s;
  memset(&s, 0, sizeof(s));

  s.round = 0;
  assert(Pio25CardAbstraction().num_buckets(nullptr, s) == 169);
  assert(Pio49CardAbstraction().num_buckets(nullptr, s) == 169);
  assert(Pio85CardAbstraction().num_buckets(nullptr, s) == 169);

  s.round = 1;
  assert(Pio25CardAbstraction().num_buckets(nullptr, s) == 169 * 25);
  assert(Pio49CardAbstraction().num_buckets(nullptr, s) == 169 * 49);
  assert(Pio85CardAbstraction().num_buckets(nullptr, s) == 169 * 85);

  s.round = 2;
  assert(Pio25CardAbstraction().num_buckets(nullptr, s) == 169 * 47);
  assert(Pio49CardAbstraction().num_buckets(nullptr, s) == 169 * 47);
  assert(Pio85CardAbstraction().num_buckets(nullptr, s) == 169 * 47);

  s.round = 3;
  assert(Pio25CardAbstraction().num_buckets(nullptr, s) == 169 * 46);
  assert(Pio49CardAbstraction().num_buckets(nullptr, s) == 169 * 46);
  assert(Pio85CardAbstraction().num_buckets(nullptr, s) == 169 * 46);
}

int main() {
  check_round_counts();
  return 0;
}
