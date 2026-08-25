#ifndef __PURE_CFR_CARD_ABSTRACTION_HPP__
#define __PURE_CFR_CARD_ABSTRACTION_HPP__

/* card_abstraction.hpp
 * Richard Gibson, Jun 28, 2013
 *
 * Home of the card_abstraction abstract class and all implementing classes
 *
 * Copyright (C) 2013 by Richard Gibson
 */

/* C / C++ / STL indluces */
#include <vector>

/* project_acpc_server includes */
extern "C" {
#include "acpc_server_code/game.h"
}

/* Pure CFR includes */
#include "constants.hpp"
#include "betting_node.hpp"

/* Base class */
class CardAbstraction {
public:

  CardAbstraction( );
  virtual ~CardAbstraction( );

  virtual int num_buckets( const Game *game, const BettingNode *node ) const = 0;
  virtual int num_buckets( const Game *game, const State &state ) const = 0;
  virtual int get_bucket( const Game *game,
			  const BettingNode *node,
			  const uint8_t board_cards[ MAX_BOARD_CARDS ],
			  const uint8_t hole_cards[ MAX_PURE_CFR_PLAYERS ]
			  [ MAX_HOLE_CARDS ] ) const = 0;
  virtual bool can_precompute_buckets( ) const { return false; }
  virtual void precompute_buckets( const Game *game,
				   hand_t &hand ) const;

protected:
};

/* The null card abstraction treats every set of cards as its own bucket.
 * This is a naive abstraction that does not take suit isomorphism into account.
 * Further, more buckets are used than necessary as card removal and order
 * are ignored.
 */
class NullCardAbstraction : public CardAbstraction {
public:

  NullCardAbstraction( const Game *game );
  virtual ~NullCardAbstraction( );

  virtual int num_buckets( const Game *game, const BettingNode *node ) const;
  virtual int num_buckets( const Game *game, const State &state ) const;
  virtual int get_bucket( const Game *game,
			  const BettingNode *node,
			  const uint8_t board_cards[ MAX_BOARD_CARDS ],
			  const uint8_t hole_cards[ MAX_PURE_CFR_PLAYERS ]
			  [ MAX_HOLE_CARDS ] ) const;
  virtual bool can_precompute_buckets( ) const { return true; }
  virtual void precompute_buckets( const Game *game,
				   hand_t &hand ) const;

protected:
  virtual int get_bucket_internal( const Game *game,
				   const uint8_t board_cards[ MAX_BOARD_CARDS ],
				   const uint8_t hole_cards[ MAX_PURE_CFR_PLAYERS ]
				   [ MAX_HOLE_CARDS ],
				   const int player,
				   const int round ) const;
  
  const int deck_size;
  int m_num_buckets[ MAX_ROUNDS ];
};

/* The blind card abstraction treats every set of cards as the same.
 * This is a simple abstraction that enforces the agent to not look at its cards.
 */
class BlindCardAbstraction : public CardAbstraction {
public:

  BlindCardAbstraction( );
  virtual ~BlindCardAbstraction( );

  virtual int num_buckets( const Game *game, const BettingNode *node ) const;
  virtual int num_buckets( const Game *game, const State &state ) const;
  virtual int get_bucket( const Game *game,
			  const BettingNode *node,
			  const uint8_t board_cards[ MAX_BOARD_CARDS ],
			  const uint8_t hole_cards[ MAX_PURE_CFR_PLAYERS ]
			  [ MAX_HOLE_CARDS ] ) const;
  virtual bool can_precompute_buckets( ) const { return true; }
  virtual void precompute_buckets( const Game *game,
				   hand_t &hand ) const;
};

/* A flop-only 25-bucket post-flop abstraction.
 * The lookup table maps each canonical 3-card flop to a landmark bucket in
 * [0, 24].  Non-flop rounds remain coarse/blind so the abstraction can be
 * tested incrementally without exploding memory.
 */
class Pio25CardAbstraction : public CardAbstraction {
public:

  Pio25CardAbstraction( );
  virtual ~Pio25CardAbstraction( );

  virtual int num_buckets( const Game *game, const BettingNode *node ) const;
  virtual int num_buckets( const Game *game, const State &state ) const;
  virtual int get_bucket( const Game *game,
			  const BettingNode *node,
			  const uint8_t board_cards[ MAX_BOARD_CARDS ],
			  const uint8_t hole_cards[ MAX_PURE_CFR_PLAYERS ]
			  [ MAX_HOLE_CARDS ] ) const;
  virtual bool can_precompute_buckets( ) const { return true; }
  virtual void precompute_buckets( const Game *game,
				   hand_t &hand ) const;

protected:
  bool load_flop_map( const char *filename );
  int canonical_flop_index( const uint8_t board_cards[ MAX_BOARD_CARDS ] ) const;
  int flops_to_bucket( const uint8_t board_cards[ MAX_BOARD_CARDS ] ) const;
  int public_board_bucket( const uint8_t board_cards[ MAX_BOARD_CARDS ],
			   const int round ) const;
  int public_board_bucket_count( const int round ) const;
  int preflop_to_bucket( const uint8_t hole_cards[ MAX_PURE_CFR_PLAYERS ]
			    [ MAX_HOLE_CARDS ],
			    const int player ) const;

  std::vector<int> flop_bucket_map;
  static const int NUM_PIO25_BUCKETS = 25;
  static const int NUM_PRE_FLOP_BUCKETS = 169;
  static const int NUM_CANONICAL_FLOPS = 22100;
};

class Pio49CardAbstraction : public Pio25CardAbstraction {
public:

  Pio49CardAbstraction( );
  virtual ~Pio49CardAbstraction( );

  virtual int num_buckets( const Game *game, const BettingNode *node ) const;
  virtual int num_buckets( const Game *game, const State &state ) const;
  virtual int get_bucket( const Game *game,
			  const BettingNode *node,
			  const uint8_t board_cards[ MAX_BOARD_CARDS ],
			  const uint8_t hole_cards[ MAX_PURE_CFR_PLAYERS ]
			  [ MAX_HOLE_CARDS ] ) const;
  virtual bool can_precompute_buckets( ) const { return true; }
  virtual void precompute_buckets( const Game *game,
				   hand_t &hand ) const;

protected:
  bool load_flop_map( const char *filename );
  int flops_to_bucket( const uint8_t board_cards[ MAX_BOARD_CARDS ] ) const;

  std::vector<int> flop_bucket_map;
  static const int NUM_PIO49_BUCKETS = 49;
  static const int NUM_PRE_FLOP_BUCKETS = 169;
  static const int NUM_CANONICAL_FLOPS = 22100;
};

class Pio85CardAbstraction : public Pio49CardAbstraction {
public:

  Pio85CardAbstraction( );
  virtual ~Pio85CardAbstraction( );

  virtual int num_buckets( const Game *game, const BettingNode *node ) const;
  virtual int num_buckets( const Game *game, const State &state ) const;
  virtual int get_bucket( const Game *game,
			  const BettingNode *node,
			  const uint8_t board_cards[ MAX_BOARD_CARDS ],
			  const uint8_t hole_cards[ MAX_PURE_CFR_PLAYERS ]
			  [ MAX_HOLE_CARDS ] ) const;
  virtual bool can_precompute_buckets( ) const { return true; }
  virtual void precompute_buckets( const Game *game,
				   hand_t &hand ) const;

protected:
  bool load_flop_map( const char *filename );
  int flops_to_bucket( const uint8_t board_cards[ MAX_BOARD_CARDS ] ) const;

  std::vector<int> flop_bucket_map;
  static const int NUM_PIO85_BUCKETS = 85;
  static const int NUM_PRE_FLOP_BUCKETS = 169;
  static const int NUM_CANONICAL_FLOPS = 22100;
};

#endif
