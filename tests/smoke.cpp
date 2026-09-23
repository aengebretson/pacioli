#include <luca/ledger.hpp>

int main() {
    const luca::Ledger ledger;
    return ledger.empty() ? 0 : 1;
}
