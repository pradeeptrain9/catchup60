/**
 * What you can catch up on. Live games first, then finished ones, then the
 * offline fixture — an order the backend decides, so this component only
 * renders it.
 */
import React from 'react';
import {Pressable, StyleSheet, Text, View} from 'react-native';
import {TVFocusGuideView} from '@amazon-devices/react-native-kepler';

import {getOrigin, originLabel, type Game} from '../api';

type Props = {
  games: Game[];
  onPick: (game: Game) => void;
  onSwitchOrigin: () => void;
};

export const GameList = ({games, onPick, onSwitchOrigin}: Props) => {
  const firstPlayable = games.findIndex((game) => game.playable);

  return (
    <TVFocusGuideView style={styles.list} autoFocus>
      {/* Which backend answered this list, labelled with where it would go
          rather than where it is — a row saying "AWS" while showing local
          data is the one thing worse than no row at all.

          Above the games, not below them. Below, it was the last child of a
          list whose length is not ours to choose: however many games are on,
          plus the fixture. At five games it rendered past the bottom of a
          1080-line screen and could not be reached at all. Focus still starts
          on the first playable game, because that Pressable asks for it
          explicitly and hasTVPreferredFocus outranks document order. */}
      <Pressable
        testID="origin-switch"
        onPress={onSwitchOrigin}
        style={({focused}) => [styles.switchRow, focused && styles.rowOn]}>
        {({focused}) => (
          <>
            <Text style={[styles.switchText, focused && styles.statusOn]}>
              Source: {originLabel(getOrigin())}
            </Text>
            <Text style={[styles.switchHint, focused && styles.statusOn]}>
              switch to {originLabel(getOrigin() === 'local' ? 'cloud' : 'local')}
            </Text>
          </>
        )}
      </Pressable>

      {games.map((game, index) => {
        if (!game.playable) {
          // Shown, not offered: a scheduled game has no plays to recap, and
          // hiding it would leave the viewer wondering where tonight's game is.
          return (
            <View
              key={game.id}
              testID={`game-${game.id}`}
              style={[styles.row, styles.rowDim]}>
              <Text style={styles.teamsDim}>
                {game.away} at {game.home}
              </Text>
              <Text style={styles.statusDim}>{game.status}</Text>
            </View>
          );
        }
        return (
          <Pressable
            key={game.id}
            testID={`game-${game.id}`}
            hasTVPreferredFocus={index === firstPlayable}
            onPress={() => onPick(game)}
            style={({focused}) => [styles.row, focused && styles.rowOn]}>
            {({focused}) => (
              <>
                <Text style={[styles.teams, focused && styles.teamsOn]}>
                  {game.away} at {game.home}
                </Text>
                <View style={styles.meta}>
                  {game.live && <Text style={styles.live}>LIVE</Text>}
                  <Text style={[styles.status, focused && styles.statusOn]}>
                    {game.status}
                  </Text>
                </View>
              </>
            )}
          </Pressable>
        );
      })}
    </TVFocusGuideView>
  );
};

const styles = StyleSheet.create({
  // Flows from the top rather than centring. Centring looked better at four
  // rows and overflowed at five — the focused card grew upward over the
  // header — and the row count is not ours to choose: it is however many
  // games are on, plus the fixture. The source switch is first rather than
  // last for the same reason: anything after the games is the thing that
  // falls off the bottom when the slate is long.
  list: {flex: 1, justifyContent: 'flex-start', gap: 12},
  row: {flexDirection: 'row', alignItems: 'center',
        justifyContent: 'space-between', paddingHorizontal: 32,
        paddingVertical: 16, borderRadius: 10, backgroundColor: '#0d1117',
        borderWidth: 2, borderColor: '#21262d'},
  rowOn: {backgroundColor: '#f0f6fc', borderColor: '#f0f6fc'},
  rowDim: {backgroundColor: 'transparent', borderColor: '#161b22'},
  teams: {color: '#f0f6fc', fontSize: 28},
  teamsOn: {color: '#07090f', fontWeight: '600'},
  teamsDim: {color: '#484f58', fontSize: 24},
  meta: {flexDirection: 'row', alignItems: 'center', gap: 16},
  live: {color: '#ff7b72', fontSize: 16, fontWeight: '800',
         letterSpacing: 1.4},
  status: {color: '#8b949e', fontSize: 20},
  statusOn: {color: '#424a53'},
  statusDim: {color: '#484f58', fontSize: 18},
  switchRow: {flexDirection: 'row', alignItems: 'center',
              justifyContent: 'space-between', paddingHorizontal: 32,
              paddingVertical: 14, borderRadius: 10, marginBottom: 10,
              backgroundColor: 'transparent', borderWidth: 2,
              borderColor: '#161b22'},
  switchText: {color: '#8b949e', fontSize: 20},
  switchHint: {color: '#484f58', fontSize: 18},
});
