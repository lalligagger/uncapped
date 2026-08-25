#include "card_abstraction.hpp"

Pio85CardAbstraction::Pio85CardAbstraction( )
{
  flop_bucket_map.clear( );
  bool loaded = load_flop_map( "pio85_flop_map.dat" );
  if( !loaded ) {
    fprintf( stderr,
             "Warning: PIO85 flop map not found; using PIO49-style zero bucket mapping.\n" );
    flop_bucket_map.assign( NUM_CANONICAL_FLOPS, 0 );
  }
}

Pio85CardAbstraction::~Pio85CardAbstraction( )
{
}

bool Pio85CardAbstraction::load_flop_map( const char *filename )
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

int Pio85CardAbstraction::num_buckets( const Game *game,
				       const BettingNode *node ) const
{
  if( node == NULL ) {
    return 1;
  }
  if( node->get_round() == 0 ) {
    return NUM_PRE_FLOP_BUCKETS;
  }
  if( node->get_round() == 1 ) {
    return NUM_PRE_FLOP_BUCKETS * NUM_PIO85_BUCKETS;
  }
  if( node->get_round() == 2 ) {
    return NUM_PRE_FLOP_BUCKETS * 47;
  }
  if( node->get_round() == 3 ) {
    return NUM_PRE_FLOP_BUCKETS * 46;
  }
  return 1;
}

int Pio85CardAbstraction::num_buckets( const Game *game,
				       const State &state ) const
{
  if( state.round == 0 ) {
    return NUM_PRE_FLOP_BUCKETS;
  }
  if( state.round == 1 ) {
    return NUM_PRE_FLOP_BUCKETS * NUM_PIO85_BUCKETS;
  }
  if( state.round == 2 ) {
    return NUM_PRE_FLOP_BUCKETS * 47;
  }
  if( state.round == 3 ) {
    return NUM_PRE_FLOP_BUCKETS * 46;
  }
  return 1;
}

int Pio85CardAbstraction::flops_to_bucket( const uint8_t board_cards[ MAX_BOARD_CARDS ] ) const
{
  if( flop_bucket_map.empty() ) {
    return 0;
  }

  int flop_idx = Pio25CardAbstraction::canonical_flop_index( board_cards );
  if( flop_idx < 0 || flop_idx >= ( int ) flop_bucket_map.size() ) {
    return 0;
  }

  int bucket = flop_bucket_map[ flop_idx ];
  if( bucket < 0 ) {
    bucket = 0;
  }
  if( bucket >= NUM_PIO85_BUCKETS ) {
    bucket = NUM_PIO85_BUCKETS - 1;
  }
  return bucket;
}

int Pio85CardAbstraction::get_bucket( const Game *game,
				      const BettingNode *node,
				      const uint8_t board_cards[ MAX_BOARD_CARDS ],
				      const uint8_t hole_cards[ MAX_PURE_CFR_PLAYERS ]
				      [ MAX_HOLE_CARDS ] ) const
{
  if( node == NULL ) {
    return 0;
  }
  const int hole_bucket = preflop_to_bucket( hole_cards, node->get_player() );
  const int round = node->get_round();
  if( round == 0 ) {
    return hole_bucket;
  }

  const int board_bucket = Pio25CardAbstraction::public_board_bucket( board_cards, round );
  const int board_bucket_count = Pio25CardAbstraction::public_board_bucket_count( round );
  return hole_bucket * board_bucket_count + board_bucket;
}

void Pio85CardAbstraction::precompute_buckets( const Game *game,
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
