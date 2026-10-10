/**
 * Plays a recap: one card per segment, animated against the manifest's clock.
 *
 * The clock is the manifest's and not the audio element's, because the Vega
 * Virtual Device cannot play audio — its sink never initializes, the element
 * reports MEDIA_ERR_SRC_NOT_SUPPORTED, and currentTime reads NaN. Since the
 * manifest's segment timings are measured from the real synthesized audio, the
 * two agree wherever audio does work, and the recap stays correct where it
 * does not.
 */
import React, {useCallback, useEffect, useRef, useState} from 'react';
import {Animated, Pressable, StyleSheet, Text, View} from 'react-native';

import {audioUrl, type Manifest} from '../api';

type Props = {
  manifest: Manifest;
  onAgain: () => void;
  onBack: () => void;
};

export const RecapPlayer = ({manifest, onAgain, onBack}: Props) => {
  const [position, setPosition] = useState(0);
  const [finished, setFinished] = useState(false);
  const [audioNote, setAudioNote] = useState('');
  const fade = useRef(new Animated.Value(0)).current;
  const rise = useRef(new Animated.Value(0)).current;
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  const animateIn = useCallback(() => {
    fade.setValue(0);
    rise.setValue(16);
    Animated.parallel([
      Animated.timing(fade, {toValue: 1, duration: 280,
                             useNativeDriver: true}),
      Animated.timing(rise, {toValue: 0, duration: 280,
                             useNativeDriver: true}),
    ]).start();
  }, [fade, rise]);

  useEffect(() => {
    animateIn();
    manifest.segments.forEach((segment, index) => {
      if (index === 0) {
        return;
      }
      timers.current.push(
        setTimeout(() => {
          setPosition(index);
          animateIn();
        }, segment.start * 1000),
      );
    });
    timers.current.push(
      setTimeout(() => setFinished(true), manifest.totalSeconds * 1000),
    );

    // Audio rides along where the platform supports it. Its failure is
    // expected on the simulator and must never interrupt the recap.
    const url = audioUrl(manifest);
    let player: any = null;
    if (url) {
      (async () => {
        try {
          const {AudioPlayer} = await import(
            '@amazon-devices/react-native-w3cmedia'
          );
          player = new AudioPlayer();
          await player.initialize();
          player.addEventListener('error', () =>
            setAudioNote('narration unavailable on this device'),
          );
          player.src = url;
          player.autoplay = false;
          await player.play();
        } catch {
          setAudioNote('narration unavailable on this device');
        }
      })();
    }

    return () => {
      timers.current.forEach(clearTimeout);
      timers.current = [];
      player?.deinitialize?.().catch(() => undefined);
    };
  }, [manifest, animateIn]);

  const segment = manifest.segments[position];
  const elapsed = segment ? segment.start + segment.dur : 0;
  const progress = Math.max(0, Math.min(1, elapsed / manifest.totalSeconds));
  const plays = manifest.segments.filter((s) => s.kind === 'play');
  const playNumber = segment?.kind === 'play'
    ? plays.findIndex((s) => s.playIndex === segment.playIndex) + 1
    : 0;

  if (finished) {
    return (
      <View style={styles.center}>
        <Text style={styles.done}>
          {manifest.gameStatus === 'Final'
            ? "That's the game."
            : "You're caught up."}
        </Text>
        <View style={styles.buttons}>
          <Pressable
            hasTVPreferredFocus
            onPress={onAgain}
            style={({focused}) => [styles.button, focused && styles.buttonOn]}>
            {({focused}) => (
              <Text style={[styles.buttonText, focused && styles.buttonTextOn]}>
                Catch up again
              </Text>
            )}
          </Pressable>
          <Pressable
            onPress={onBack}
            style={({focused}) => [styles.button, focused && styles.buttonOn]}>
            {({focused}) => (
              <Text style={[styles.buttonText, focused && styles.buttonTextOn]}>
                Other games
              </Text>
            )}
          </Pressable>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.area}>
      <Animated.View
        style={[styles.card, {opacity: fade, transform: [{translateY: rise}]}]}>
        <Text style={styles.kind}>
          {segment?.kind === 'play'
            ? `What you missed · ${playNumber} of ${plays.length}`
            : segment?.kind}
        </Text>
        <Text testID="card-text" style={styles.cardText}>
          {segment?.text}
        </Text>
      </Animated.View>

      <View>
        <View style={styles.track}>
          <View style={[styles.fill, {flex: progress}]} />
          <View style={{flex: 1 - progress}} />
        </View>
        <View style={styles.footer}>
          <Text testID="engine-note" style={styles.footText}>
            {manifest.engine.runsExplained} of {manifest.engine.runsTotal} runs
            {'  ·  '}
            {manifest.engine.selected} of {manifest.engine.considered} plays
          </Text>
          {audioNote !== '' && (
            <Text testID="audio-note" style={styles.footNote}>
              {audioNote}
            </Text>
          )}
        </View>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  area: {flex: 1, justifyContent: 'center', gap: 44},
  card: {backgroundColor: '#0d1117', borderLeftWidth: 5,
         borderLeftColor: '#2f81f7', borderRadius: 8, padding: 36},
  kind: {color: '#2f81f7', fontSize: 15, fontWeight: '700', letterSpacing: 1.6,
         textTransform: 'uppercase', marginBottom: 14},
  cardText: {color: '#f0f6fc', fontSize: 34, lineHeight: 46},
  track: {flexDirection: 'row', height: 5, backgroundColor: '#161b22',
          borderRadius: 3, overflow: 'hidden'},
  fill: {backgroundColor: '#2f81f7'},
  footer: {flexDirection: 'row', justifyContent: 'space-between',
           marginTop: 14},
  footText: {color: '#6e7681', fontSize: 16},
  footNote: {color: '#6e7681', fontSize: 16, fontStyle: 'italic'},
  center: {flex: 1, alignItems: 'center', justifyContent: 'center', gap: 32},
  done: {color: '#f0f6fc', fontSize: 38},
  buttons: {flexDirection: 'row', gap: 20},
  button: {paddingHorizontal: 40, paddingVertical: 18, borderRadius: 10,
           backgroundColor: '#161b22', borderWidth: 2, borderColor: '#30363d'},
  buttonOn: {backgroundColor: '#f0f6fc', borderColor: '#f0f6fc'},
  buttonText: {color: '#f0f6fc', fontSize: 24, fontWeight: '600'},
  buttonTextOn: {color: '#07090f'},
});
