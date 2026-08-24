/* card_abstraction.cpp
 * Richard Gibson, Jun 28, 2013
 *
 * Home of the card_abstraction abstract class and all implementing classes
 *
 * Copyright (C) 2013 by Richard Gibson
 */

/* C / C++ / STL indluces */

/* project_acpc_server includes */
extern "C" {
}

/* Pure CFR includes */
#include "card_abstraction.hpp"

CardAbstraction::CardAbstraction( )
{
}

CardAbstraction::~CardAbstraction( )
{
}

/* By default, assume cannot precompute buckets */
void CardAbstraction::precompute_buckets( const Game *game, hand_t &hand ) const
{
  fprintf( stderr, "precompute_buckets called for base "
	   "card abstraction class!\n" );
  assert( false );
}

NullCardAbstraction::NullCardAbstraction( const Game *game )
  : deck_size( game->numSuits * game->numRanks )
{
  /* Precompute number of buckets per round */
  m_num_buckets[ 0 ] = 1;
  for( int i = 0; i < game->numHoleCards; ++i ) {
    m_num_buckets[ 0 ] *= deck_size;
  }
  for( int r = 0; r < MAX_ROUNDS; ++r ) {
    if( r < game->numRounds ) {
      if( r > 0 ) {
	m_num_buckets[ r ] = m_num_buckets[ r - 1 ];
      }
      for( int i = 0; i < game->numBoardCards[ r ]; ++i ) {
	m_num_buckets[ r ] *= deck_size;
      }
    } else {
      m_num_buckets[ r ] = 0;
    }
  }
}

NullCardAbstraction::~NullCardAbstraction( )
{
}

int NullCardAbstraction::num_buckets( const Game *game,
				      const BettingNode *node ) const
{
  return m_num_buckets[ node->get_round() ];
}

int NullCardAbstraction::num_buckets( const Game *game,
				      const State &state ) const
{
  return m_num_buckets[ state.round ];
}

int NullCardAbstraction::get_bucket( const Game *game,
				     const BettingNode *node,
				     const uint8_t board_cards[ MAX_BOARD_CARDS ],
				     const uint8_t hole_cards
				     [ MAX_PURE_CFR_PLAYERS ]
				     [ MAX_HOLE_CARDS ] ) const
{
  return get_bucket_internal( game, board_cards, hole_cards,
			      node->get_player(), node->get_round() );
}

void NullCardAbstraction::precompute_buckets( const Game *game,
					      hand_t &hand ) const
{
  for( int p = 0; p < game->numPlayers; ++p ) {
    for( int r = 0; r < game->numRounds; ++r ) {
      hand.precomputed_buckets[ p ][ r ] = get_bucket_internal( game,
								hand.board_cards,
								hand.hole_cards,
								p, r );
    }
  }
}

int NullCardAbstraction::get_bucket_internal( const Game *game,
					      const uint8_t board_cards
					      [ MAX_BOARD_CARDS ],
					      const uint8_t hole_cards
					      [ MAX_PURE_CFR_PLAYERS ]
					      [ MAX_HOLE_CARDS ],
					      const int player,
					      const int round ) const
{
  /* Calculate the unique bucket number for this hand */
  int bucket = 0;
  for( int i = 0; i < game->numHoleCards; ++i ) {
    if( i > 0 ) {
      bucket *= deck_size;
    }
    uint8_t card = hole_cards[ player ][ i ];
    bucket += rankOfCard( card ) * game->numSuits + suitOfCard( card );
  }
  for( int r = 0; r <= round; ++r ) {
    for( int i = bcStart( game, r ); i < sumBoardCards( game, r ); ++i ) {
      bucket *= deck_size;
      uint8_t card = board_cards[ i ];
      bucket += rankOfCard( card ) * game->numSuits + suitOfCard( card );
    }
  }

  return bucket;
}

BlindCardAbstraction::BlindCardAbstraction( )
{
}

BlindCardAbstraction::~BlindCardAbstraction( )
{
}

int BlindCardAbstraction::num_buckets( const Game *game,
				       const BettingNode *node ) const
{
  return 1;
}

int BlindCardAbstraction::num_buckets( const Game *game,
				       const State &state ) const
{
  return 1;
}

int BlindCardAbstraction::get_bucket( const Game *game,
				      const BettingNode *node,
				      const uint8_t board_cards
				      [ MAX_BOARD_CARDS ],
				      const uint8_t hole_cards
				      [ MAX_PURE_CFR_PLAYERS ]
				      [ MAX_HOLE_CARDS ] ) const
{
  return 0;
}

void BlindCardAbstraction::precompute_buckets( const Game *game, hand_t &hand ) const
{
  for( int p = 0; p < game->numPlayers; ++p ) {
    for( int r = 0; r < game->numRounds; ++r ) {
      hand.precomputed_buckets[ p ][ r ] = 0;
    }
  }
}

Pio25CardAbstraction::Pio25CardAbstraction( )
{
  flop_bucket_map.clear( );
  bool loaded = load_flop_map( "pio25_flop_map.dat" );
  if( !loaded ) {
    loaded = load_flop_map( "flop_map.dat" );
  }
  if( !loaded ) {
    fprintf( stderr,
             "Warning: PIO25 flop map not found; using all-zero bucket mapping.\n" );
    flop_bucket_map.assign( NUM_CANONICAL_FLOPS, 0 );
  }
}

Pio25CardAbstraction::~Pio25CardAbstraction( )
{
}

bool Pio25CardAbstraction::load_flop_map( const char *filename )
{
  FILE *file = fopen( filename, "r" );
  if( file == NULL ) {
    return false;
  }

  std::vector<int> loaded_map;
  loaded_map.reserve( NUM_CANONICAL_FLOPS );

  int value = 0;
  while( fscanf( file, "%d", &value ) == 1 ) {
    loaded_map.push_back( value );
    if( loaded_map.size() >= NUM_CANONICAL_FLOPS ) {
      break;
    }
  }
  fclose( file );

  if( loaded_map.size() != NUM_CANONICAL_FLOPS ) {
    fprintf( stderr, "Warning: [%s] contained %zu entries; expected %d.\n",
             filename, loaded_map.size(), NUM_CANONICAL_FLOPS );
    return false;
  }

  flop_bucket_map = loaded_map;
  return true;
}

int Pio25CardAbstraction::canonical_flop_index( const uint8_t board_cards[ MAX_BOARD_CARDS ] ) const
{
  uint8_t cards[ 3 ];
  cards[ 0 ] = board_cards[ 0 ];
  cards[ 1 ] = board_cards[ 1 ];
  cards[ 2 ] = board_cards[ 2 ];

  for( int i = 0; i < 2; ++i ) {
    for( int j = i + 1; j < 3; ++j ) {
      if( cards[ i ] > cards[ j ] ) {
        uint8_t tmp = cards[ i ];
        cards[ i ] = cards[ j ];
        cards[ j ] = tmp;
      }
    }
  }

  int idx = 0;
  for( int a = 0; a < 52; ++a ) {
    for( int b = a + 1; b < 52; ++b ) {
      for( int c = b + 1; c < 52; ++c ) {
        if( a == cards[ 0 ] && b == cards[ 1 ] && c == cards[ 2 ] ) {
          return idx;
        }
        ++idx;
      }
    }
  }

  return 0;
}

int Pio25CardAbstraction::flops_to_bucket( const uint8_t board_cards[ MAX_BOARD_CARDS ] ) const
{
  if( flop_bucket_map.empty() ) {
    return 0;
  }

  int flop_idx = canonical_flop_index( board_cards );
  if( flop_idx < 0 || flop_idx >= ( int ) flop_bucket_map.size() ) {
    return 0;
  }

  int bucket = flop_bucket_map[ flop_idx ];
  if( bucket < 0 ) {
    bucket = 0;
  }
  if( bucket >= NUM_PIO25_BUCKETS ) {
    bucket = NUM_PIO25_BUCKETS - 1;
  }
  return bucket;
}

int Pio25CardAbstraction::preflop_to_bucket( const uint8_t hole_cards
					       [ MAX_PURE_CFR_PLAYERS ]
					       [ MAX_HOLE_CARDS ],
					       const int player ) const
{
  const int r0 = rankOfCard( hole_cards[ player ][ 0 ] );
  const int r1 = rankOfCard( hole_cards[ player ][ 1 ] );
  const int lo = std::min( r0, r1 );
  const int hi = std::max( r0, r1 );

  /*
   * Bucket layout:
   *  - 0..12: pocket pairs (22, 33, ..., AA)
   *  - 13..168: unique non-pair rank classes, split as offsuit/suited.
   *
   * We keep 23 and 32 as the same bucket, but distinguish 23o from 23s.
   * This matches the ACPC local card model and the random deal combinatorics:
   * for a given rank pair, there are 12 offsuit combos and 4 suited combos.
   */
  if( lo == hi ) {
    return lo;
  }

  int pair_index = 0;
  for( int high = 2; high <= 14; ++high ) {
    for( int low = 2; low < high; ++low ) {
      if( low == lo && high == hi ) {
	const bool suited = suitOfCard( hole_cards[ player ][ 0 ] ) ==
	  suitOfCard( hole_cards[ player ][ 1 ] );
	return 13 + 2 * pair_index + ( suited ? 1 : 0 );
      }
      ++pair_index;
    }
  }

  return 0;
}

int Pio25CardAbstraction::num_buckets( const Game *game,
				       const BettingNode *node ) const
{
  if( node == NULL ) {
    return 1;
  }
  if( node->get_round() == 0 ) {
    return NUM_PRE_FLOP_BUCKETS;
  }
  if( node->get_round() == 1 ) {
    return NUM_PIO25_BUCKETS;
  }
  return 1;
}

int Pio25CardAbstraction::num_buckets( const Game *game,
				       const State &state ) const
{
  if( state.round == 0 ) {
    return NUM_PRE_FLOP_BUCKETS;
  }
  if( state.round == 1 ) {
    return NUM_PIO25_BUCKETS;
  }
  return 1;
}

int Pio25CardAbstraction::get_bucket( const Game *game,
				      const BettingNode *node,
				      const uint8_t board_cards[ MAX_BOARD_CARDS ],
				      const uint8_t hole_cards[ MAX_PURE_CFR_PLAYERS ]
				      [ MAX_HOLE_CARDS ] ) const
{
  if( node == NULL ) {
    return 0;
  }
  if( node->get_round() == 0 ) {
    return preflop_to_bucket( hole_cards, node->get_player() );
  }
  if( node->get_round() == 1 ) {
    return flops_to_bucket( board_cards );
  }
  return 0;
}

void Pio25CardAbstraction::precompute_buckets( const Game *game,
					      hand_t &hand ) const
{
  for( int p = 0; p < game->numPlayers; ++p ) {
    for( int r = 0; r < game->numRounds; ++r ) {
      if( r == 0 ) {
        hand.precomputed_buckets[ p ][ r ] = preflop_to_bucket( hand.hole_cards, p );
      } else if( r == 1 ) {
        hand.precomputed_buckets[ p ][ r ] = flops_to_bucket( hand.board_cards );
      } else {
        hand.precomputed_buckets[ p ][ r ] = 0;
      }
    }
  }
}
