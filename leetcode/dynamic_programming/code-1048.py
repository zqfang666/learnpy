# 1048. Longest String Chain
# Given a list of words, each word consists of English lowercase letters.

# Let's say word1 is a predecessor of word2 if and only if we can add exactly one letter anywhere
#  in word1 to make it equal to word2.  For example, "abc" is a predecessor of "abac".

# A word chain is a sequence of words [word_1, word_2, ..., word_k] with k >= 1, 
# where word_1 is a predecessor of word_2, word_2 is a predecessor of word_3, and so on.

# Return the longest possible length of a word chain with words chosen from the given list of words.


# Example 1:

# Input: ["a","b","ba","bca","bda","bdca"]
# Output: 4
# Explanation: one of the longest word chain is "a","ba","bda","bdca".


# Note:

# 1 <= words.length <= 1000
# 1 <= words[i].length <= 16
# words[i] only consists of English lowercase letters.
import collections


def longestStrChain(words: "List[str]") -> int:
    dct = collections.defaultdict(set)
    for w in words:
        dct[len(w)].add(w)
    res = {w: 1 for w in words}
    for length in sorted(dct, reverse=True):
        if length - 1 in dct:
            for word in dct[length]:
                subset = {word[:i] + word[i + 1:] for i in range(len(word))}
                ava_set = dct[length - 1] & subset
                for m in ava_set:
                    res[m] = max(res[word] + 1, res[m])

    return max(res.values())