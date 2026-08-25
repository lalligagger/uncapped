#include <assert.h>
#include <stdint.h>

#include "card_abstraction.hpp"

int main() {
  Pio25CardAbstraction abstraction;
  uint8_t hole_cards[MAX_PURE_CFR_PLAYERS][MAX_HOLE_CARDS] = {0};

  // ACPC rank encoding: 2..A are 0..12, so A-K is (12,11) and should map to
  // the paired AK offset in the 0..12 rank space.
  hole_cards[0][0] = makeCard(12, 0);
  hole_cards[0][1] = makeCard(11, 1);

  int bucket = abstraction.preflop_to_bucket(hole_cards, 0);
  assert(bucket == 167 || bucket == 168);

  hole_cards[0][0] = makeCard(11, 0);
  hole_cards[0][1] = makeCard(12, 1);
  bucket = abstraction.preflop_to_bucket(hole_cards, 0);
  assert(bucket == 167 || bucket == 168);

  return 0;
}
